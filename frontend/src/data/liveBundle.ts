import { zipSync } from 'fflate';
import type { MessageKey } from '../i18n/messages';

// Canli isin girdi paketini tarayicida kurar. Sunucu tarafi sozlesme
// backend/live_contracts.py icindeki InputManifest: sema 1, modul `imaging`,
// hastalik `glioma`, tam dort NIfTI hacmi (T1, T1CE, T2, FLAIR), her biri rol
// `volume`. Arsivde `input.json` ve bildirilen dosyalardan baskasi bulunamaz.
//
// Reddi burada vermek onemli: sunucuya gitmeden once soylenen "FLAIR eksik",
// yuklemeden sonra donen 422'den cok daha anlasilir. Yine de bu bir kolaylik
// katmani; asil karar sunucunun.

export const MODALITIES = ['T1', 'T1CE', 'T2', 'FLAIR'] as const;
export type Modality = (typeof MODALITIES)[number];

export type BundleProblem =
  | 'missing-modality'
  | 'not-nifti'
  | 'empty-file'
  | 'too-large';

export const bundleProblemKeys: Record<BundleProblem, MessageKey> = {
  'missing-modality': 'live.upload.missingModality',
  'not-nifti': 'live.upload.notNifti',
  'empty-file': 'live.upload.emptyFile',
  'too-large': 'live.upload.tooLarge',
};

export class BundleRejected extends Error {
  readonly problem: BundleProblem;
  /** Sorunun hangi modaliteden geldigi; genel sorunlarda bos kalir. */
  readonly modality?: Modality;

  constructor(problem: BundleProblem, modality?: Modality) {
    super(problem);
    this.name = 'BundleRejected';
    this.problem = problem;
    this.modality = modality;
  }

  get messageKey(): MessageKey {
    return bundleProblemKeys[this.problem];
  }
}

export type VolumeSelection = Partial<Record<Modality, File>>;

/** Sunucunun `MERGEN_MAX_UPLOAD_BYTES` varsayilaniyla ayni buyukluk sinifi. */
export const MAX_BUNDLE_BYTES = 512 * 1024 * 1024;

const NIFTI = /\.nii(\.gz)?$/i;

/**
 * Dosya adi vaka kimligi degildir: hasta adi tasiyabilecek kullanici dosya adi
 * arsive girmez. Her hacim modalitesine gore sabit bir ada yazilir.
 */
export function memberName(modality: Modality, fileName: string): string {
  return `${modality.toLowerCase()}${fileName.toLowerCase().endsWith('.nii') ? '.nii' : '.nii.gz'}`;
}

export function inspect(selection: VolumeSelection): BundleRejected | null {
  for (const modality of MODALITIES) {
    const file = selection[modality];
    if (!file) return new BundleRejected('missing-modality', modality);
    if (!NIFTI.test(file.name)) return new BundleRejected('not-nifti', modality);
    if (file.size === 0) return new BundleRejected('empty-file', modality);
  }
  const total = MODALITIES.reduce((sum, modality) => sum + (selection[modality]?.size ?? 0), 0);
  if (total > MAX_BUNDLE_BYTES) return new BundleRejected('too-large');
  return null;
}

/**
 * Secimi `POST /api/live/jobs` gövdesi olan ZIP'e cevirir.
 *
 * Uyelerin hepsi *stored*: `.nii.gz` zaten sikistirilmis, yeniden sikistirmak
 * tarayicida saniyeler yer ve neredeyse hicbir bayt kazandirmaz. `input.json`
 * kucuk oldugu icin onun da farki yok.
 */
export async function buildBundle(selection: VolumeSelection): Promise<Blob> {
  const problem = inspect(selection);
  if (problem) throw problem;
  const entries: Record<string, [Uint8Array, { level: 0 }]> = {};
  const files: { path: string; role: 'volume'; modality: Modality }[] = [];
  for (const modality of MODALITIES) {
    const file = selection[modality]!;
    const path = memberName(modality, file.name);
    entries[path] = [new Uint8Array(await file.arrayBuffer()), { level: 0 }];
    files.push({ path, role: 'volume', modality });
  }
  const manifest = { schemaVersion: 1, module: 'imaging', disease: 'glioma', files };
  entries['input.json'] = [new TextEncoder().encode(JSON.stringify(manifest)), { level: 0 }];
  return new Blob([zipSync(entries) as unknown as BlobPart], { type: 'application/zip' });
}
