#!/usr/bin/env python3
"""Train the MERGEN gated Attention-MIL head with checkpoint/resume support.

Run directory layout::

    <run_dir>/config.json          resolved arguments + split hash + features dir
    <run_dir>/train_log.jsonl      one line per epoch (losses, metrics, lr, time)
    <run_dir>/status.json          live status for terminal/agent monitoring
    <run_dir>/last.pt              every epoch (model, optimizer, scheduler, RNG, counters)
    <run_dir>/best.pt              best validation macro-F1
    <run_dir>/epoch_XXX.pt         every --save-every epochs (archive)
    <run_dir>/interrupt.pt         written on SIGINT/SIGTERM before exiting with code 130

``--resume auto`` continues from interrupt.pt, else last.pt, if the stored split hash,
features dir and model config match; otherwise it refuses so that a different
experiment is never silently merged into an old run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import signal
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset import CLASSES, FeatureBagDataset, apply_qc, class_weights, collate_single, load_cohort, load_split, split_hash  # noqa: E402
from metrics import compute_metrics  # noqa: E402
from model import GatedAttentionMIL  # noqa: E402


def data_root() -> Path:
    configured = os.environ.get("MERGEN_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path.home() / "mergen-data"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def rng_state() -> dict:
    return {"python": random.getstate(), "numpy": np.random.get_state(), "torch": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None}


def restore_rng(state: dict) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"])
    if state.get("cuda") is not None and torch.cuda.is_available():
        torch.cuda.set_rng_state_all(state["cuda"])


def run_eval(model, loader, device, criterion):
    model.eval()
    probs, labels, losses, pids = [], [], [], []
    with torch.inference_mode():
        for feats, label, pid in loader:
            feats = feats.to(device, non_blocking=True)
            y = torch.tensor([label], device=device)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, _ = model(feats)
            logits = logits.float()
            losses.append(float(criterion(logits, y)))
            probs.append(torch.softmax(logits, dim=1)[0].cpu().numpy())
            labels.append(label)
            pids.append(pid)
    metrics = compute_metrics(np.array(labels), np.stack(probs))
    metrics["loss"] = float(np.mean(losses))
    return metrics, {"patient_id": pids, "label": labels, "probs": [p.tolist() for p in probs]}


def save_checkpoint(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", default=str(data_root() / "pathology/splits/splits_v1.json"))
    p.add_argument("--cohort", default=str(data_root() / "pathology/datasets/tcga_glioma/manifests/cohort.tsv"))
    p.add_argument("--features-dir", default=str(data_root() / "pathology/features/dinov2_vitb14_224_0.5mpp"))
    p.add_argument("--run-dir", required=True)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--bag-size", type=int, default=4096)
    p.add_argument("--eval-tiles", type=int, default=None, help="cap tiles at eval (default: all stored)")
    p.add_argument("--hidden", type=int, default=256)
    p.add_argument("--attn-dim", type=int, default=128)
    p.add_argument("--dropout", type=float, default=0.25)
    p.add_argument("--patience", type=int, default=15, help="early stopping on val macro-F1")
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--seed", type=int, default=20260914)
    p.add_argument("--resume", default="auto", help="auto | none | path to checkpoint")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--allow-missing-features", action="store_true", help="train on the subset of patients that have features (preflight)")
    p.add_argument("--min-tiles", type=int, default=100, help="QC: exclude slides with fewer stored tissue tiles (faint/empty scans)")
    p.add_argument("--train-patients", nargs="*", default=None, help="override train ids (preflight)")
    p.add_argument("--val-patients", nargs="*", default=None, help="override val ids (preflight)")
    args = p.parse_args()

    run_dir = Path(args.run_dir).expanduser()
    run_dir.mkdir(parents=True, exist_ok=True)
    split = load_split(Path(args.split))
    cohort = load_cohort(Path(args.cohort))
    labels = {pid: cohort[pid]["class"] for pid in cohort}
    train_ids = args.train_patients or split["splits"]["train"]
    val_ids = args.val_patients or split["splits"]["val"]
    features_dir = Path(args.features_dir).expanduser()
    train_ids, excluded_train = apply_qc(features_dir, train_ids, args.min_tiles)
    val_ids, excluded_val = apply_qc(features_dir, val_ids, args.min_tiles)
    missing = [p for p, r in {**excluded_train, **excluded_val}.items() if r.startswith("no_features")]
    if missing and not args.allow_missing_features:
        raise SystemExit(f"features missing for {len(missing)} patients (e.g. {missing[:5]}); run extract_embeddings.py or pass --allow-missing-features")
    for name, exc in (("train", excluded_train), ("val", excluded_val)):
        if exc:
            tqdm.write(f"QC excluded {len(exc)} {name} slides: " + ", ".join(f"{k} [{v}]" for k, v in exc.items()))
    if not train_ids or not val_ids:
        raise SystemExit("empty train or val set")
    model_cfg = {"in_dim": 768, "hidden": args.hidden, "attn_dim": args.attn_dim, "n_classes": len(CLASSES), "dropout": args.dropout}
    config = {"args": vars(args), "split_hash": split_hash(split), "split_file": str(args.split), "features_dir": str(features_dir), "model": model_cfg, "n_train": len(train_ids), "n_val": len(val_ids), "class_counts_train": {c: sum(1 for i in train_ids if labels[i] == c) for c in CLASSES}, "class_counts_val": {c: sum(1 for i in val_ids if labels[i] == c) for c in CLASSES}, "qc_min_tiles": args.min_tiles, "qc_excluded_train": excluded_train, "qc_excluded_val": excluded_val, "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    identity = {"split_hash": config["split_hash"], "features_dir": config["features_dir"], "model": model_cfg, "bag_size": args.bag_size, "seed": args.seed}

    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = GatedAttentionMIL(**model_cfg).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=args.lr * 0.05)
    weights = class_weights([labels[i] for i in train_ids]).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    train_ds = FeatureBagDataset(features_dir, train_ids, labels, bag_size=args.bag_size, train=True, seed=args.seed)
    val_ds = FeatureBagDataset(features_dir, val_ids, labels, bag_size=None, train=False, seed=args.seed, max_eval_tiles=args.eval_tiles)
    train_loader = DataLoader(train_ds, batch_size=1, shuffle=True, num_workers=args.workers, collate_fn=collate_single, pin_memory=device.type == "cuda", persistent_workers=args.workers > 0)
    val_loader = DataLoader(val_ds, batch_size=1, shuffle=False, num_workers=min(args.workers, 2), collate_fn=collate_single, pin_memory=device.type == "cuda")

    start_epoch, best_f1, best_epoch, bad_epochs, history = 0, -1.0, -1, 0, []
    resume_path = None
    if args.resume == "auto":
        for name in ("interrupt.pt", "last.pt"):
            if (run_dir / name).is_file():
                resume_path = run_dir / name
                break
    elif args.resume not in ("none", ""):
        resume_path = Path(args.resume)
    if resume_path:
        ck = torch.load(resume_path, map_location="cpu", weights_only=False)
        if ck["identity"] != identity:
            raise SystemExit(f"refusing to resume {resume_path}: identity mismatch\nstored={ck['identity']}\ncurrent={identity}")
        model.load_state_dict(ck["model"])
        optimizer.load_state_dict(ck["optimizer"])
        scheduler.load_state_dict(ck["scheduler"])
        restore_rng(ck["rng"])
        start_epoch = ck["epoch"] + 1
        best_f1, best_epoch, bad_epochs, history = ck["best_f1"], ck["best_epoch"], ck["bad_epochs"], ck["history"]
        tqdm.write(f"resumed from {resume_path.name}: next epoch {start_epoch}, best macro-F1 {best_f1:.4f} @ {best_epoch}")
    else:
        (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n")
        (run_dir / "train_log.jsonl").write_text("")

    interrupted = {"flag": False}

    def handle(signum, frame):
        interrupted["flag"] = True
        tqdm.write(f"signal {signum}: will save interrupt.pt after the current step")

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    def checkpoint_payload(epoch: int) -> dict:
        return {"identity": identity, "epoch": epoch, "model": model.state_dict(), "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "rng": rng_state(), "best_f1": best_f1, "best_epoch": best_epoch, "bad_epochs": bad_epochs, "history": history, "model_config": model_cfg, "classes": CLASSES, "saved": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    def write_status(epoch: int, phase: str, extra: dict | None = None) -> None:
        payload = {"run_dir": str(run_dir), "phase": phase, "epoch": epoch, "epochs": args.epochs, "best_macro_f1": best_f1, "best_epoch": best_epoch, "bad_epochs": bad_epochs, "patience": args.patience, "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if extra:
            payload.update(extra)
        (run_dir / "status.json").write_text(json.dumps(payload, indent=2) + "\n")

    for epoch in range(start_epoch, args.epochs):
        model.train()
        train_ds.set_epoch(epoch)
        t0 = time.time()
        losses, correct = [], 0
        bar = tqdm(train_loader, desc=f"epoch {epoch + 1}/{args.epochs}", unit="slide", leave=False)
        for step, (feats, label, pid) in enumerate(bar):
            feats = feats.to(device, non_blocking=True)
            y = torch.tensor([label], device=device)
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, _ = model(feats)
                loss = criterion(logits.float(), y)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            losses.append(loss.item())
            correct += int(logits.argmax(1).item() == label)
            if step % 25 == 0:
                bar.set_postfix(loss=f"{np.mean(losses):.3f}", acc=f"{correct / (step + 1):.3f}")
            if interrupted["flag"]:
                break
        if interrupted["flag"]:
            save_checkpoint(run_dir / "interrupt.pt", checkpoint_payload(epoch - 1))
            write_status(epoch, "interrupted", {"note": "resume with --resume auto"})
            tqdm.write("interrupt.pt written; exiting (130)")
            sys.exit(130)
        scheduler.step()
        val_metrics, _ = run_eval(model, val_loader, device, criterion)
        train_loss = float(np.mean(losses))
        improved = val_metrics["macro_f1"] > best_f1
        if improved:
            best_f1, best_epoch, bad_epochs = val_metrics["macro_f1"], epoch, 0
        else:
            bad_epochs += 1
        record = {"epoch": epoch, "train_loss": round(train_loss, 5), "train_acc": round(correct / len(train_ds), 4), "val": {k: (round(v, 5) if isinstance(v, float) else v) for k, v in val_metrics.items() if k != "confusion_matrix"}, "val_confusion": val_metrics["confusion_matrix"], "lr": optimizer.param_groups[0]["lr"], "seconds": round(time.time() - t0, 1), "improved": improved, "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        history.append(record)
        with (run_dir / "train_log.jsonl").open("a") as handle:
            handle.write(json.dumps(record) + "\n")
        save_checkpoint(run_dir / "last.pt", checkpoint_payload(epoch))
        if improved:
            save_checkpoint(run_dir / "best.pt", checkpoint_payload(epoch))
        if args.save_every and (epoch + 1) % args.save_every == 0:
            save_checkpoint(run_dir / f"epoch_{epoch + 1:03d}.pt", checkpoint_payload(epoch))
        if (run_dir / "interrupt.pt").is_file():
            (run_dir / "interrupt.pt").unlink()
        write_status(epoch + 1, "training", {"last_train_loss": train_loss, "last_val": record["val"], "epoch_seconds": record["seconds"]})
        tqdm.write(f"epoch {epoch + 1:3d} | train loss {train_loss:.4f} acc {record['train_acc']:.3f} | val loss {val_metrics['loss']:.4f} macroF1 {val_metrics['macro_f1']:.4f} balAcc {val_metrics['balanced_accuracy']:.4f} AUROC {val_metrics['auroc_macro_ovr']:.4f} MCC {val_metrics['mcc']:.4f} | {'*' if improved else ' '} best {best_f1:.4f}@{best_epoch + 1} | {record['seconds']:.1f}s")
        if bad_epochs >= args.patience:
            tqdm.write(f"early stopping: no improvement for {args.patience} epochs")
            break
    write_status(min(epoch + 1, args.epochs), "finished", {"best_checkpoint": str(run_dir / "best.pt")})
    (run_dir / "best_metrics.json").write_text(json.dumps({"best_epoch": best_epoch, "best_val_macro_f1": best_f1, "history_len": len(history)}, indent=2) + "\n")
    tqdm.write(f"done: best val macro-F1 {best_f1:.4f} at epoch {best_epoch + 1}; checkpoints in {run_dir}")


if __name__ == "__main__":
    main()
