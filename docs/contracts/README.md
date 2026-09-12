# Canlı iş sözleşmesi v1

Tarayıcı, `input.json` ve orada bildirilen dosyaları tek ZIP olarak
`POST /api/live/jobs` ucuna gönderir. Görüntü/glioma profili tam olarak birer T1,
T1CE, T2 ve FLAIR NIfTI hacmi ister. Genomik profil dosya istemez; varyantı ve
protein dizisi ya da UniProt erişimini `input.json` içinde taşır.
İstek gövdesi multipart değildir; ZIP doğrudan `Content-Type: application/zip`
ile akış halinde gönderilir ve boyut sınırı veri alınırken uygulanır.

GPU worker sonucu `manifest.json` ve bildirilen tüm varlıkları içeren tek ZIP olarak
özel worker API'sine yükler. Canlı sonuçta `hasGroundTruth` daima `false` olur.
Worker sonuç ZIP'ini de doğrudan `application/zip` gövdesi olarak gönderir.
Görüntü sonucu en az `report-json`, `prediction-nifti` ve `prediction-glb`; genomik
sonuç en az `report-json` varlığı içerir. Her varlığın SHA-256 ve byte boyutu
yüklemede doğrulanır.

Bu dizindeki değerler yalnız sözleşme örneğidir; hasta kaydı, gerçek tahmin veya
model metriği değildir. Asıl doğrulama `backend/live_contracts.py` içindeki Pydantic
modelleriyle yapılır.

Hazır demo paketleri canlı iş ZIP'lerinden ayrıdır. Kök katalog örneği
`demo-catalog.v3.example.json`, görüntü koleksiyonu örneği
`demo-imaging-manifest.v3.example.json` dosyasındadır. Katalog yalnız modül,
hastalık ve göreli manifest yolunu taşır; API bu disk yolunu tarayıcıya açmaz.
