"""One-shot cleanup invoked by the VPS systemd timer."""
from backend.live_store import LiveSettings, LiveStore


if __name__ == "__main__":
    try:
        settings = LiveSettings.from_env()
    except ValueError as exc:
        raise SystemExit(f"Cleanup refused: {exc}") from None
    print(LiveStore(settings).cleanup())
