import { describe, expect, it } from 'vitest';
import { unzipSync } from 'fflate';
import {
  buildBundle,
  inspect,
  MAX_BUNDLE_BYTES,
  MODALITIES,
  type Modality,
  type VolumeSelection,
} from '../data/liveBundle';

const volume = (name: string, bytes = 8) =>
  new File([new Uint8Array(bytes).fill(1)], name, { type: 'application/gzip' });

const complete = (): VolumeSelection => ({
  T1: volume('sub-01_T1w.nii.gz'),
  T1CE: volume('sub-01_T1ce.nii.gz'),
  T2: volume('sub-01_T2w.nii.gz'),
  FLAIR: volume('sub-01_FLAIR.nii.gz'),
});

const members = async (selection: VolumeSelection) => {
  const bundle = await buildBundle(selection);
  return unzipSync(new Uint8Array(await bundle.arrayBuffer()));
};

describe('live input bundle', () => {
  it('carries input.json and the four declared volumes, and nothing else', async () => {
    // Sunucu bildirilmemis tek bir uyeyi bile reddediyor.
    const archive = await members(complete());
    expect(Object.keys(archive).sort()).toEqual(
      ['flair.nii.gz', 'input.json', 't1.nii.gz', 't1ce.nii.gz', 't2.nii.gz'].sort(),
    );
  });

  it('writes the manifest the backend contract requires', async () => {
    const archive = await members(complete());
    const manifest = JSON.parse(new TextDecoder().decode(archive['input.json']));
    expect(manifest).toEqual({
      schemaVersion: 1,
      module: 'imaging',
      disease: 'glioma',
      files: [
        { path: 't1.nii.gz', role: 'volume', modality: 'T1' },
        { path: 't1ce.nii.gz', role: 'volume', modality: 'T1CE' },
        { path: 't2.nii.gz', role: 'volume', modality: 'T2' },
        { path: 'flair.nii.gz', role: 'volume', modality: 'FLAIR' },
      ],
    });
    const declared = manifest.files.map((file: { path: string }) => file.path);
    expect(new Set([...declared, 'input.json'])).toEqual(new Set(Object.keys(archive)));
  });

  it('keeps the chosen file name out of the archive', async () => {
    // Kullanici dosya adi vaka kimligi degildir ve hasta adi tasiyabilir.
    const selection = complete();
    selection.T1 = volume('AYSE_YILMAZ_1985_T1.nii.gz');
    const archive = await members(selection);
    expect(Object.keys(archive)).not.toContain('AYSE_YILMAZ_1985_T1.nii.gz');
    const text = new TextDecoder().decode(archive['input.json']);
    expect(text).not.toContain('AYSE');
    expect(text).not.toContain('YILMAZ');
  });

  it('keeps a plain .nii volume as .nii', async () => {
    const selection = complete();
    selection.T2 = volume('scan_T2.nii');
    const archive = await members(selection);
    expect(Object.keys(archive)).toContain('t2.nii');
    expect(Object.keys(archive)).not.toContain('t2.nii.gz');
  });

  it('names the missing modality instead of refusing in general', async () => {
    for (const modality of MODALITIES) {
      const selection = complete();
      delete selection[modality];
      const problem = inspect(selection);
      expect(problem?.problem).toBe('missing-modality');
      expect(problem?.modality).toBe(modality);
      await expect(buildBundle(selection)).rejects.toMatchObject({ modality });
    }
  });

  it('refuses a file that is not NIfTI, and says which one', async () => {
    const selection = complete();
    selection.FLAIR = volume('flair.dcm');
    expect(inspect(selection)).toMatchObject({ problem: 'not-nifti', modality: 'FLAIR' });
  });

  it('refuses an empty volume rather than uploading a placeholder', async () => {
    const selection = complete();
    selection.T1CE = volume('t1ce.nii.gz', 0);
    expect(inspect(selection)).toMatchObject({ problem: 'empty-file', modality: 'T1CE' });
  });

  it('accepts a selection the server would accept', async () => {
    // Sunucu varsayilani 2 GiB (backend/live_store.py). Istemci esigi bunun
    // altina cekilirse gecerli bir yukleme tarayicida bosuna reddedilir.
    const selection = complete();
    selection.T1 = { name: 'big.nii.gz', size: 1024 ** 3 } as File;
    expect(inspect(selection)).toBeNull();
  });

  it('refuses a selection over the upload limit before it is sent', async () => {
    const selection = complete();
    const huge = { name: 'big.nii.gz', size: MAX_BUNDLE_BYTES + 1 } as File;
    selection.T1 = huge;
    expect(inspect(selection)).toMatchObject({ problem: 'too-large' });
    expect(inspect(selection)?.modality).toBeUndefined();
  });

  it('gives every rejection a dictionary message', async () => {
    const { tr } = await import('../i18n/messages');
    const { bundleProblemKeys } = await import('../data/liveBundle');
    for (const key of Object.values(bundleProblemKeys)) expect(tr[key].trim()).not.toBe('');
  });

  it('accepts the four modalities in any selection order', async () => {
    const reversed: VolumeSelection = {};
    for (const modality of [...MODALITIES].reverse() as Modality[])
      reversed[modality] = volume(`${modality}.nii.gz`);
    expect(inspect(reversed)).toBeNull();
    const archive = await members(reversed);
    expect(Object.keys(archive)).toHaveLength(5);
  });
});
