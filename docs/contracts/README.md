# Canlı iş sözleşmesi v1

Tarayıcı, `input.json` ve orada bildirilen dosyaları tek ZIP olarak
`POST /api/live/jobs` ucuna gönderir. Görüntü/glioma profili tam olarak birer T1,
T1CE, T2 ve FLAIR NIfTI hacmi ister. Genomik profil dosya istemez; varyantı ve
protein dizisi ya da UniProt erişimini `input.json` içinde taşır.

GPU worker sonucu `manifest.json` ve bildirilen tüm varlıkları içeren tek ZIP olarak
özel worker API'sine yükler. Canlı sonuçta `hasGroundTruth` daima `false` olur.
Görüntü sonucu en az `report-json`, `prediction-nifti` ve `prediction-glb`; genomik
sonuç en az `report-json` varlığı içerir. Her varlığın SHA-256 ve byte boyutu
yüklemede doğrulanır.

Bu dizindeki değerler yalnız sözleşme örneğidir; hasta kaydı, gerçek tahmin veya
model metriği değildir. Asıl doğrulama `backend/live_contracts.py` içindeki Pydantic
modelleriyle yapılır.
