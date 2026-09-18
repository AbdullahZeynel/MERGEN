import { describe, it, expect } from 'vitest';
import { liveJobSchema, liveReportSchema, liveResultSchema } from '../data/contracts.live';
import { makeLiveJob, makeLiveReport, makeLiveResult, makeReviewFlag } from './fixtures';

describe('live job boundary validation', () => {
  it('accepts the shape the backend actually returns', () => {
    expect(liveJobSchema.safeParse(makeLiveJob()).success).toBe(true);
  });

  it('refuses a reference label on a live case', () => {
    // Canli vakada referans etiketi yoktur. Kabul edilse arayuz Dice gosterir
    // ve olculmemis bir sayi olculmus gibi okunur.
    const result = { ...makeLiveResult(), hasGroundTruth: true };
    expect(liveResultSchema.safeParse(result).success).toBe(false);
  });

  it('refuses a result that is missing a required asset', () => {
    for (const kind of ['report-json', 'prediction-nifti', 'prediction-glb']) {
      const result = makeLiveResult();
      result.assets = result.assets.filter((asset) => asset.kind !== kind);
      expect(liveResultSchema.safeParse(result).success).toBe(false);
    }
  });

  it('refuses assets belonging to another job', () => {
    const job = makeLiveJob();
    job.assetUrls = { 'report.json': '/api/live/jobs/' + 'b'.repeat(32) + '/assets/report.json' };
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('refuses a demo path smuggled into a live job', () => {
    const job = makeLiveJob();
    job.assetUrls!['report.json'] = '/api/demo/cases/UCSF-0001/slices/axial/77';
    expect(liveJobSchema.safeParse(job).success).toBe(false);
    const other = makeLiveJob();
    other.downloadUrl = '/api/demo/cases/UCSF-0001/mesh';
    expect(liveJobSchema.safeParse(other).success).toBe(false);
  });

  it('refuses an external download link', () => {
    const job = makeLiveJob();
    job.downloadUrl = 'https://example.com/result.zip';
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('refuses a result whose identity does not match the job', () => {
    const job = makeLiveJob();
    job.result!.jobId = 'c'.repeat(32);
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('refuses a result on a job that has not completed', () => {
    for (const status of ['queued', 'claimed', 'running', 'failed', 'cancelled'] as const) {
      const job = makeLiveJob();
      job.status = status;
      expect(liveJobSchema.safeParse(job).success).toBe(false);
    }
  });

  it('refuses a completed job that carries no result', () => {
    const job = makeLiveJob();
    delete job.result;
    delete job.downloadUrl;
    delete job.assetUrls;
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('refuses a download link on a job that is still queued', () => {
    const job = makeLiveJob();
    job.status = 'queued';
    delete job.result;
    delete job.assetUrls;
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('refuses an error code outside a failed job', () => {
    const job = makeLiveJob();
    job.errorCode = 'model-unavailable';
    expect(liveJobSchema.safeParse(job).success).toBe(false);
  });

  it('accepts a failed job with its error code and nothing else', () => {
    const job = makeLiveJob();
    job.status = 'failed';
    job.errorCode = 'model-unavailable';
    delete job.result;
    delete job.downloadUrl;
    delete job.assetUrls;
    expect(liveJobSchema.safeParse(job).success).toBe(true);
  });

  it('refuses an unsupported module or disease profile', () => {
    for (const patch of [{ module: 'pathology' }, { disease: 'meningioma' }]) {
      expect(liveJobSchema.safeParse({ ...makeLiveJob(), ...patch }).success).toBe(false);
    }
  });
});

describe('live report boundary validation', () => {
  it('accepts the report the runner writes', () => {
    expect(liveReportSchema.safeParse(makeLiveReport()).success).toBe(true);
  });

  it('refuses region volumes that do not fit inside the whole tumour', () => {
    // TC ya da ET, WT'yi asamaz; asan bir sayi ekranda sessizce yanlis okunur.
    for (const patch of [{ TC: 50_000 }, { ET: 50_000 }]) {
      const report = makeLiveReport();
      Object.assign(report.regionVolumes, patch);
      expect(liveReportSchema.safeParse(report).success).toBe(false);
    }
  });

  it('refuses a report from an older runner schema', () => {
    const report = { ...makeLiveReport(), schemaVersion: 1 };
    expect(liveReportSchema.safeParse(report).success).toBe(false);
  });

  it('keeps the evidence numbers a flag has to carry', () => {
    const report = makeLiveReport();
    report.reviewFlags = [makeReviewFlag()];
    expect(liveReportSchema.safeParse(report).success).toBe(true);
    const missing = makeLiveReport();
    missing.reviewFlags = [
      { ...makeReviewFlag(), evidence: {} as never },
    ];
    expect(liveReportSchema.safeParse(missing).success).toBe(false);
  });
});
