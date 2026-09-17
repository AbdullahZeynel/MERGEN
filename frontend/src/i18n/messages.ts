// Arayuzun butun metinleri burada. Turkce sozluk anahtar kumesini tanimlar;
// `en` ondan turetilen bir Record oldugu icin eksik ceviri derleme hatasidir.
export const tr = {
  'app.title': 'MERGEN · Vaka çalışma alanı',
  'app.description':
    'MERGEN onkoloji karar destek prototipi. Hazır vakalar için beyin MR görüntüleme çalışma alanı.',
  'app.skip': 'Çalışma alanına geç',
  'app.nav': 'Ana gezinme',
  'app.brand': 'MERGEN çalışma alanı',
  'app.wordmarkSub': 'ONKOLOJİ KARAR DESTEĞİ',

  'theme.toLight': 'Açık temaya geç',
  'theme.toDark': 'Koyu temaya geç',
  'theme.light': 'Açık',
  'theme.dark': 'Koyu',

  'language.switch': 'Switch interface language to English',
  'language.short': 'EN',

  'cases.hide': 'Vaka listesini gizle',
  'cases.show': 'Vaka listesini göster',
  'cases.close': 'Vaka listesini kapat',
  'cases.title': 'Vakalar',
  'cases.pick': 'İncelemek için bir vaka seçin.',
  'cases.sourceLabel': 'Veri kaynağı',
  'cases.demo': 'Hazır demo',
  'cases.live': 'Canlı analiz',
  'cases.search': 'Vaka ara',
  'cases.searchPlaceholder': 'Vaka kimliği ile ara',
  'cases.listLabel': 'VAKA LİSTESİ',
  'cases.filter': 'Vaka durumunu filtrele',
  'cases.allStatuses': 'Tüm durumlar',
  'cases.loading': 'Vakalar yükleniyor…',
  'cases.modality': 'MR görüntüleme',
  'cases.listFailed': 'Vaka listesi alınamadı.',
  'cases.noMatch': 'Eşleşen vaka bulunamadı.',

  'status.demo_ready': 'Hazır demo',
  'status.draft': 'Girdi bekliyor',
  'status.queued': 'Kuyrukta',
  'status.processing': 'İşleniyor',
  'status.completed': 'Tamamlandı',
  'status.failed': 'Başarısız',

  'axis.axial': 'Aksiyel',
  'axis.coronal': 'Koronal',
  'axis.sagittal': 'Sagittal',

  'workspace.breadcrumb': 'Çalışma alanı',
  'workspace.showCases': 'Vakaları göster',
  'workspace.eyebrow': 'VAKA İNCELEME',
  'workspace.emptyTitle': 'Vaka çalışma alanı',
  'workspace.emptyBody': 'Vaka verileri hazır olduğunda burada görüntülenir.',
  'workspace.modeDemo': 'HAZIR DEMO',
  'workspace.modeLive': 'CANLI ANALİZ',
  'workspace.waiting': 'Servis yanıtı bekleniyor',
  'workspace.demoUnreachable': 'Demo servisine ulaşılamadı',
  'workspace.liveDisconnected': 'Analiz servisi bağlı değil',
  'workspace.demoListed': 'Demo vaka listesi alındı',
  'workspace.liveListed': 'Canlı vaka listesi alındı',
  'workspace.refresh': 'Vaka verilerini yenile',
  'workspace.loadingCase': 'Vaka verileri yükleniyor…',
  'workspace.liveNotReadyTitle': 'Canlı bağlantı henüz kurulmadı',
  'workspace.demoUnreadableTitle': 'Demo paketi okunamadı',
  'workspace.backToDemo': 'Hazır demolara dön',
  'workspace.retry': 'Yeniden dene',
  'workspace.liveNeedsServices': 'Canlı analiz için model servislerinin bağlanması gerekiyor.',
  'workspace.demoMissing':
    'Hazır vaka dosyaları bulunamadı veya geçerli değil. Demo paketinin hazırlanması gerekiyor.',
  'workspace.noCaseTitle': 'Henüz vaka yok',
  'workspace.noCaseBody': 'Bu veri kaynağında görüntülenecek vaka bulunmuyor.',

  'viewer.slices': '2D kesit görüntüleyici',
  'viewer.mesh': '3D segmentasyon',
  'viewer.expand': 'büyüt',
  'viewer.collapse': 'küçült',
  'viewer.wideView': 'geniş görünüm',
  'viewer.stage': 'Kesit görüntüsü; ok tuşlarıyla gezin',
  'viewer.sliceFailed': 'Kesit görüntüsü yüklenemedi',
  'viewer.sliceFailedBody': 'Vakanın diğer düzlemlerini görüntüleyebilirsiniz.',
  'viewer.sliceAlt': '{id} FLAIR {axis}, kesit {index}',
  'viewer.predictionAlt': 'Model tahmini segmentasyon maskesi',
  'viewer.groundTruthAlt': 'Referans segmentasyon maskesi',
  'viewer.sliceOf': 'Kesit {index} / {count}',
  'viewer.loadingShort': 'Yükleniyor…',
  'viewer.overlays': 'Segmentasyon katmanları',
  'viewer.prediction': 'Tahmin',
  'viewer.groundTruth': 'Referans',
  'viewer.plane': 'Görüntü düzlemi',
  'viewer.previousSlice': 'Önceki kesit',
  'viewer.nextSlice': 'Sonraki kesit',
  'viewer.pickSlice': 'Kesit seç',
  'viewer.centre': 'Merkez',
  'viewer.keyboardHint': 'Kesitler arasında ok tuşlarıyla da gezinebilirsiniz.',
  'viewer.preparing': '3D görüntüleyici hazırlanıyor…',
  'viewer.preparingBody': 'Etkileşimli görüntüleyici kodu yükleniyor.',

  'mesh.ET': 'Kontrast tutan tümör',
  'mesh.TC_NCR': 'Nekrotik çekirdek',
  'mesh.ED': 'Ödem',
  'mesh.BRAIN': 'Beyin dış yüzeyi',
  'mesh.canvas': 'Etkileşimli 3D tümör modeli',
  'mesh.loading': '3D model yükleniyor…',
  'mesh.missing': '3D sonuç paketi bulunamadı',
  'mesh.webglFailed': '3D görüntüleme başlatılamadı',
  'mesh.failed': '3D model yüklenemedi',
  'mesh.webglHint': 'Tarayıcının WebGL desteğini ve donanım hızlandırmasını kontrol edin.',
  'mesh.loadingHint': 'Hazır segmentasyon verisi açılıyor.',
  'mesh.fallbackHint': 'Vakanın 2D görüntülerini incelemeye devam edebilirsiniz.',
  'mesh.resetCamera': '3D kamerayı sıfırla',
  'mesh.navHint': 'Sürükle: döndür · Tekerlek: yakınlaştır · Sağ tuş: taşı',
  'mesh.opacity': 'Tümör opaklığı',
  'mesh.brainTitle': 'MR sinyalinden yaklaşık dış yüzey; anatomik segmentasyon değildir.',

  'case.sourceEyebrow': 'VERİ KAYNAĞI',
  'case.shapeEyebrow': 'HACİM BOYUTU',
  'case.previewEyebrow': 'MEVCUT ÖNİZLEME',
  'case.resultEyebrow': 'SONUÇ TÜRÜ',
  'case.voxel': 'voxel',
  'case.previewValue': 'FLAIR · 3 düzlem',
  'case.notice': 'Örnek vaka — UCSF-PDGM. Tahmin katmanı nnU-Net ve Swin UNETR topluluğundan.',
  'case.brainNotice':
    'Dış yüzey MR sinyalinden yaklaşık üretilmiştir; anatomik segmentasyon değildir.',

  'guide.askTitle': 'Kısa bir tanıtım ister misiniz?',
  'guide.askBody':
    'Çalışma alanının bölümlerini yaklaşık bir dakikada gezelim. İstediğiniz an kapatabilir, sonra alt bilgiden tekrar açabilirsiniz.',
  'guide.accept': 'Evet, göster',
  'guide.decline': 'Hayır, doğrudan başla',
  'guide.reopen': 'Tanıtımı aç',
  'guide.step': 'Adım {index} / {count}',
  'guide.back': 'Geri',
  'guide.next': 'İleri',
  'guide.finish': 'Başla',
  'guide.close': 'Tanıtımı kapat',
  'guide.cases.title': 'Vaka listesi',
  'guide.cases.body':
    'Soldaki listeden bir vaka seçersiniz. "Hazır demo" önceden hazırlanmış örnek vakaları, "Canlı analiz" ise kendi verinizle çalıştırılacak yolu gösterir.',
  'guide.slices.title': '2D kesit görüntüleyici',
  'guide.slices.body':
    'Aksiyel, koronal ve sagittal düzlemler arasında geçiş yapar, kesitleri kaydırıcıyla veya ok tuşlarıyla gezersiniz. "Tahmin" ve "Referans" katmanlarını ayrı ayrı açıp kapatabilirsiniz.',
  'guide.mesh.title': '3D segmentasyon',
  'guide.mesh.body':
    'Tümör bölgeleri döndürülebilir bir yüzey modeline dönüşür. Her bölgeyi tek tek gizleyip gösterebilir, opaklığı değiştirebilirsiniz.',
  'guide.limits.title': 'Veri ve sınırlar',
  'guide.limits.body':
    'Görüntüler kamuya açık, kimliksizleştirilmiş bir araştırma veri kümesinden gelir ve çıktılar klinik kararda kullanılamaz. Ayrıntı ve atıflar için alt bilgideki veri kaynakları bağlantısına bakın.',

  'about.open': 'Veri kaynakları ve gizlilik',
  'about.title': 'Veri, gizlilik ve kaynaklar',
  'about.close': 'Kapat',

  'privacy.heading': 'Veri ve gizlilik',
  'privacy.lead':
    'Bu çalışma alanındaki bütün MR görüntüleri kamuya açık bir araştırma veri kümesinden gelir.',
  'privacy.deidentified':
    'Görüntüler insan katılımcılardan gelir ve veri kümesini yayımlayan The Cancer Imaging Archive tarafından kimliksizleştirilmiştir: hasta adı, kimlik numarası ve tarih gibi tanımlayıcılar kaldırılmış, yüz hatlarını taşıyan kafatası dokusu çıkarılmıştır.',
  'privacy.noUpload':
    'Bu gösterimde hasta verisi yüklenmez ve saklanmaz. Ekranda gördüğünüz vakalar önceden hazırlanmış, kimliksizleştirilmiş örneklerdir.',
  'privacy.licence':
    'Veri kümesi CC BY 4.0 ile yayımlanır; kullanımı atıf ister. Atıflar aşağıdaki kaynaklar bölümündedir.',
  'privacy.clinical':
    'Çıktılar araştırma ve geliştirme amaçlıdır. Tanı, tedavi veya herhangi bir klinik kararda kullanılamaz; bağımsız bir test kümesinde raporlanmış performans metriği bulunmamaktadır.',

  'credits.heading': 'Kaynaklar ve atıflar',
  'credits.datasetTitle': 'UCSF-PDGM — MR görüntüleri',
  'credits.datasetBody':
    'Çalışma alanındaki kesitler, segmentasyon katmanları ve 3B yüzeyler bu koleksiyondan türetilmiştir.',
  'credits.datasetCitation':
    'Calabrese, E., Villanueva-Meyer, J., Rudie, J., Rauschecker, A., Baid, U., Bakas, S., Cha, S., Mongan, J., Hess, C. (2022). The University of California San Francisco Preoperative Diffuse Glioma MRI (UCSF-PDGM) (Version 5) [dataset]. The Cancer Imaging Archive.',
  'credits.paperCitation':
    'Calabrese, E. ve ark. (2022). The UCSF Preoperative Diffuse Glioma MRI (UCSF-PDGM) Dataset. Radiology: Artificial Intelligence.',
  'credits.collection': 'Koleksiyon kaydı',
  'credits.modelsTitle': 'Modeller ve kütüphaneler',
  'credits.modelsBody':
    'Segmentasyon, MONAI Swin UNETR ve nnU-Net referans uygulamalarına dayanır; ikisi de Apache-2.0 ile dağıtılır. BraTS ön eğitim verisi kendi veri kullanım sözleşmesine tabidir.',
  'credits.licenceTitle': 'Bu yazılım',
  'credits.licenceBody':
    'MERGEN kaynak kodu Apache-2.0 ile yayımlanır. Depoya alınmış üçüncü taraf kaynak kodu kendi lisans bildirimleriyle dağıtılır.',
  'credits.full': 'Tam atıf listesi depodaki ATTRIBUTIONS.md dosyasındadır.',

  'footer.purpose': 'Onkolojide 3T · Araştırma amaçlıdır, klinik kararda kullanılamaz',
} as const;

export type MessageKey = keyof typeof tr;

export const en: Record<MessageKey, string> = {
  'app.title': 'MERGEN · Case workspace',
  'app.description':
    'MERGEN oncology decision support prototype. A brain MR imaging workspace for prepared cases.',
  'app.skip': 'Skip to workspace',
  'app.nav': 'Main navigation',
  'app.brand': 'MERGEN workspace',
  'app.wordmarkSub': 'ONCOLOGY DECISION SUPPORT',

  'theme.toLight': 'Switch to light theme',
  'theme.toDark': 'Switch to dark theme',
  'theme.light': 'Light',
  'theme.dark': 'Dark',

  'language.switch': 'Arayüz dilini Türkçeye çevir',
  'language.short': 'TR',

  'cases.hide': 'Hide case list',
  'cases.show': 'Show case list',
  'cases.close': 'Close case list',
  'cases.title': 'Cases',
  'cases.pick': 'Select a case to review.',
  'cases.sourceLabel': 'Data source',
  'cases.demo': 'Prepared demo',
  'cases.live': 'Live analysis',
  'cases.search': 'Search cases',
  'cases.searchPlaceholder': 'Search by case ID',
  'cases.listLabel': 'CASE LIST',
  'cases.filter': 'Filter by case status',
  'cases.allStatuses': 'All statuses',
  'cases.loading': 'Loading cases…',
  'cases.modality': 'MR imaging',
  'cases.listFailed': 'The case list could not be loaded.',
  'cases.noMatch': 'No matching case.',

  'status.demo_ready': 'Prepared demo',
  'status.draft': 'Awaiting input',
  'status.queued': 'Queued',
  'status.processing': 'Processing',
  'status.completed': 'Completed',
  'status.failed': 'Failed',

  'axis.axial': 'Axial',
  'axis.coronal': 'Coronal',
  'axis.sagittal': 'Sagittal',

  'workspace.breadcrumb': 'Workspace',
  'workspace.showCases': 'Show cases',
  'workspace.eyebrow': 'CASE REVIEW',
  'workspace.emptyTitle': 'Case workspace',
  'workspace.emptyBody': 'Case data appears here once it is ready.',
  'workspace.modeDemo': 'PREPARED DEMO',
  'workspace.modeLive': 'LIVE ANALYSIS',
  'workspace.waiting': 'Waiting for the service',
  'workspace.demoUnreachable': 'Demo service unreachable',
  'workspace.liveDisconnected': 'Analysis service not connected',
  'workspace.demoListed': 'Demo case list loaded',
  'workspace.liveListed': 'Live case list loaded',
  'workspace.refresh': 'Refresh case data',
  'workspace.loadingCase': 'Loading case data…',
  'workspace.liveNotReadyTitle': 'The live connection is not up yet',
  'workspace.demoUnreadableTitle': 'The demo package could not be read',
  'workspace.backToDemo': 'Back to prepared demos',
  'workspace.retry': 'Try again',
  'workspace.liveNeedsServices': 'Live analysis needs the model services to be connected.',
  'workspace.demoMissing':
    'The prepared case files are missing or invalid. The demo package needs to be built.',
  'workspace.noCaseTitle': 'No cases yet',
  'workspace.noCaseBody': 'This data source has no case to display.',

  'viewer.slices': '2D slice viewer',
  'viewer.mesh': '3D segmentation',
  'viewer.expand': 'expand',
  'viewer.collapse': 'collapse',
  'viewer.wideView': 'wide view',
  'viewer.stage': 'Slice image; use the arrow keys to move',
  'viewer.sliceFailed': 'The slice image could not be loaded',
  'viewer.sliceFailedBody': 'You can still view the other planes of this case.',
  'viewer.sliceAlt': '{id} FLAIR {axis}, slice {index}',
  'viewer.predictionAlt': 'Predicted segmentation mask',
  'viewer.groundTruthAlt': 'Reference segmentation mask',
  'viewer.sliceOf': 'Slice {index} of {count}',
  'viewer.loadingShort': 'Loading…',
  'viewer.overlays': 'Segmentation layers',
  'viewer.prediction': 'Prediction',
  'viewer.groundTruth': 'Reference',
  'viewer.plane': 'Imaging plane',
  'viewer.previousSlice': 'Previous slice',
  'viewer.nextSlice': 'Next slice',
  'viewer.pickSlice': 'Select slice',
  'viewer.centre': 'Centre',
  'viewer.keyboardHint': 'You can also move between slices with the arrow keys.',
  'viewer.preparing': 'Preparing the 3D viewer…',
  'viewer.preparingBody': 'Loading the interactive viewer code.',

  'mesh.ET': 'Enhancing tumour',
  'mesh.TC_NCR': 'Necrotic core',
  'mesh.ED': 'Oedema',
  'mesh.BRAIN': 'Outer brain surface',
  'mesh.canvas': 'Interactive 3D tumour model',
  'mesh.loading': 'Loading the 3D model…',
  'mesh.missing': 'No 3D result package found',
  'mesh.webglFailed': 'The 3D view could not start',
  'mesh.failed': 'The 3D model could not be loaded',
  'mesh.webglHint': "Check the browser's WebGL support and hardware acceleration.",
  'mesh.loadingHint': 'Opening the prepared segmentation data.',
  'mesh.fallbackHint': 'You can carry on reviewing the 2D images of this case.',
  'mesh.resetCamera': 'Reset the 3D camera',
  'mesh.navHint': 'Drag: rotate · Wheel: zoom · Right button: pan',
  'mesh.opacity': 'Tumour opacity',
  'mesh.brainTitle':
    'Outer surface approximated from the MR signal; it is not an anatomical segmentation.',

  'case.sourceEyebrow': 'DATA SOURCE',
  'case.shapeEyebrow': 'VOLUME SIZE',
  'case.previewEyebrow': 'AVAILABLE PREVIEW',
  'case.resultEyebrow': 'RESULT TYPE',
  'case.voxel': 'voxels',
  'case.previewValue': 'FLAIR · 3 planes',
  'case.notice':
    'Example case — UCSF-PDGM. The prediction layer comes from an nnU-Net and Swin UNETR ensemble.',
  'case.brainNotice':
    'The outer surface is approximated from the MR signal; it is not an anatomical segmentation.',

  'guide.askTitle': 'Would you like a short tour?',
  'guide.askBody':
    'A walk through the parts of the workspace, in about a minute. You can close it at any point and reopen it from the footer later.',
  'guide.accept': 'Yes, show me',
  'guide.decline': 'No, go straight in',
  'guide.reopen': 'Open the tour',
  'guide.step': 'Step {index} of {count}',
  'guide.back': 'Back',
  'guide.next': 'Next',
  'guide.finish': 'Start',
  'guide.close': 'Close the tour',
  'guide.cases.title': 'Case list',
  'guide.cases.body':
    'You pick a case from the list on the left. "Prepared demo" holds ready-made example cases; "Live analysis" is the path that runs on your own data.',
  'guide.slices.title': '2D slice viewer',
  'guide.slices.body':
    'Switch between the axial, coronal and sagittal planes and move through slices with the slider or the arrow keys. The "Prediction" and "Reference" layers toggle independently.',
  'guide.mesh.title': '3D segmentation',
  'guide.mesh.body':
    'The tumour regions become a surface model you can rotate. Each region can be hidden or shown on its own, and the opacity is adjustable.',
  'guide.limits.title': 'Data and limits',
  'guide.limits.body':
    'The images come from a publicly released, de-identified research dataset, and the outputs cannot be used for clinical decisions. The data sources link in the footer has the detail and the citations.',

  'about.open': 'Data sources and privacy',
  'about.title': 'Data, privacy and credits',
  'about.close': 'Close',

  'privacy.heading': 'Data and privacy',
  'privacy.lead':
    'Every MR image in this workspace comes from a publicly released research dataset.',
  'privacy.deidentified':
    'The images come from human participants and were de-identified by The Cancer Imaging Archive, which publishes the dataset: identifiers such as name, record number and dates were removed, and the skull tissue that carries facial features was stripped.',
  'privacy.noUpload':
    'No patient data is uploaded or stored in this demonstration. The cases on screen are prepared, de-identified examples.',
  'privacy.licence':
    'The dataset is published under CC BY 4.0 and its use requires attribution. The citations are in the credits below.',
  'privacy.clinical':
    'The outputs are for research and development. They cannot be used for diagnosis, treatment or any clinical decision, and no performance metric on an independent test set has been reported.',

  'credits.heading': 'Credits and attribution',
  'credits.datasetTitle': 'UCSF-PDGM — MR images',
  'credits.datasetBody':
    'The slices, segmentation layers and 3D surfaces in this workspace are derived from this collection.',
  'credits.datasetCitation':
    'Calabrese, E., Villanueva-Meyer, J., Rudie, J., Rauschecker, A., Baid, U., Bakas, S., Cha, S., Mongan, J., Hess, C. (2022). The University of California San Francisco Preoperative Diffuse Glioma MRI (UCSF-PDGM) (Version 5) [dataset]. The Cancer Imaging Archive.',
  'credits.paperCitation':
    'Calabrese, E. et al. (2022). The UCSF Preoperative Diffuse Glioma MRI (UCSF-PDGM) Dataset. Radiology: Artificial Intelligence.',
  'credits.collection': 'Collection record',
  'credits.modelsTitle': 'Models and libraries',
  'credits.modelsBody':
    'The segmentation builds on the MONAI Swin UNETR and nnU-Net reference implementations, both distributed under Apache-2.0. The BraTS pre-training data is subject to its own data use agreement.',
  'credits.licenceTitle': 'This software',
  'credits.licenceBody':
    'The MERGEN source code is released under Apache-2.0. Third-party source code vendored into the repository is distributed with its own licence notices.',
  'credits.full': 'The full attribution list is in ATTRIBUTIONS.md in the repository.',

  'footer.purpose': 'Onkolojide 3T · Research use only, not for clinical decisions',
};

export const dictionaries = { tr, en } as const;
export type Language = keyof typeof dictionaries;
export const languages = Object.keys(dictionaries) as Language[];
