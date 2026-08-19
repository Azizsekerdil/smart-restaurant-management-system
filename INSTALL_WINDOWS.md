# Windows Kurulum Kılavuzu

Bu belge, sistemin Windows 10/11 üzerinde sıfırdan kurulumunu adım adım anlatır.
Komut satırı deneyiminiz olmasa da takip edebilirsiniz.

---

## 0. En kısa yol: hazır uygulama (.exe)

Python kurmak, komut satırı kullanmak istemiyorsanız buradan başlayın.
Elinizde `Akilli Restaurant.exe` varsa:

1. Exe dosyasını **boş bir klasöre** koyun (örneğin `D:\Restaurant\Uygulama`).
   Program veritabanını, günlüklerini ve yüklenen dosyaları kendi yanında
   oluşturur.
2. Çift tıklayın. Siyah bir pencere açılır ve ilk kurulum yapılır.
3. Size ne yapmak istediğiniz sorulur:

   ```
   1) Örnek veriyle dene (menü, stok, 30 günlük satış geçmişi)
   2) Boş başla, yalnızca yönetici hesabı oluştur
   3) Atla (daha sonra kurarım)
   ```

   İlk kez deniyorsanız **1**'i seçin; hazır bir restoran verisiyle bütün
   ekranları dolu görürsünüz. Örnek veri kurulurken ekrana kullanıcı adları
   ve **o kuruluma özel, rastgele üretilmiş** bir parola yazılır; bu bilgi
   yalnızca bir kez gösterilir, not alın. Sabit bir demo parolası yoktur.
   Örnek verilerin tamamı sentetiktir, gerçek bir kişiye ait değildir.

4. Tarayıcı `http://127.0.0.1:8000` adresinde kendiliğinden açılır.
5. Programı durdurmak için siyah pencerede **Ctrl+C** yapın veya pencereyi
   kapatın.

**Masaüstü kısayolu** oluşturmak için (kaynak kodunuz varsa):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_app.ps1 -StartMenu
```

### Sık sorulanlar

| Soru | Yanıt |
|------|-------|
| Windows "bilinmeyen yayıncı" uyarısı verdi | Paket dijital olarak imzalanmamıştır. **Ek bilgi → Yine de çalıştır** deyin. |
| 8000 portu doluysa? | Program bunu algılar ve bir sonraki boş portu kullanır; adresi pencerede yazar. |
| Verilerimi nasıl yedeklerim? | Exe'nin yanındaki `restaurant.sqlite3`, `media` ve `.env` dosyalarını kopyalayın. Program kapalıyken kopyalayın. |
| Ayarları nereden değiştiririm? | Exe'nin yanındaki `.env` dosyası. Değişiklikten sonra programı yeniden başlatın. |
| Yapay zekâ özellikleri çalışmıyor | `.env` içinde sağlayıcıyı açmanız gerekir; bkz. [AI_INTEGRATION.md](AI_INTEGRATION.md). |
| AI Geliştirme Merkezi görünmüyor | Paketlenmiş sürümde bilinçli olarak kapalıdır; geliştirme kurulumunda kullanılır. |

Kaynak koddan kurmak veya geliştirme yapmak istiyorsanız aşağıdan devam edin.

---

## 1. Ön hazırlık

### 1.1 Python kurulumu

1. [python.org/downloads](https://www.python.org/downloads/windows/) adresinden
   **Python 3.12** (veya 3.11) indirin.
2. Kurulum ekranında **"Add python.exe to PATH"** kutusunu mutlaka işaretleyin.
3. Kurulumdan sonra PowerShell açıp doğrulayın:

   ```powershell
   python --version
   ```

   `Python 3.11.x` veya `3.12.x` görmelisiniz.

> **Not:** Python 3.13/3.14 kullanıyorsanız bazı paketlerin hazır sürümü
> (wheel) henüz olmayabilir ve derleme hatası alabilirsiniz. 3.11 veya 3.12
> önerilir.

### 1.2 Git kurulumu (isteğe bağlı)

Yalnızca kaynak kodu depodan çekecekseniz veya AI Geliştirme Merkezi'nin git
özelliklerini kullanacaksanız gerekir:
[git-scm.com/download/win](https://git-scm.com/download/win)

---

## 2. Otomatik kurulum (önerilen)

Proje klasörünü `D:\Restaurant` konumuna yerleştirin ve PowerShell'de:

```powershell
cd D:\Restaurant
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

Script sırasıyla:

1. Python sürümünü kontrol eder
2. `.venv` sanal ortamını oluşturur
3. Bağımlılıkları yükler
4. `.env` dosyasını `.env.example`'dan oluşturur ve **güvenli bir
   `DJANGO_SECRET_KEY` üretir**
5. Veritabanı tablolarını oluşturur (`migrate`)
6. Statik dosyaları toplar
7. Yönetici hesabı oluşturmanızı ister
8. İsterseniz demo veriyi yükler
9. LM Studio bağlantısını kontrol eder

### Kurulumdan sonra

```powershell
.\run_app.bat
```

Tarayıcı `http://127.0.0.1:8000` adresinde açılır.

---

## 3. Elle kurulum

Otomatik script çalışmazsa adımları tek tek uygulayın:

```powershell
# 1) Proje klasörüne gidin
cd D:\Restaurant

# 2) Sanal ortam oluşturun
python -m venv .venv

# 3) Sanal ortamı etkinleştirin
.\.venv\Scripts\Activate.ps1

# 4) Bağımlılıkları yükleyin
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5) Ortam dosyasını oluşturun
Copy-Item .env.example .env

# 6) Güvenli bir gizli anahtar üretin
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
#    Çıkan değeri .env içindeki DJANGO_SECRET_KEY satırına yapıştırın.

# 7) Veritabanını oluşturun
python manage.py migrate

# 8) Yönetici hesabı açın
python manage.py createsuperuser

# 9) (İsteğe bağlı) Demo veri yükleyin
python manage.py seed_demo

# 10) Sunucuyu başlatın
python manage.py runserver
```

---

## 4. PowerShell script çalıştırma sorunu

Şu hatayı alırsanız:

```
... yüklenemiyor çünkü bu sistemde betik çalıştırılması devre dışı bırakıldı.
```

Yalnızca bu oturum için izin verin (kalıcı bir sistem değişikliği yapmaz):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Veya scripti doğrudan bypass ile çağırın:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

---

## 5. Veritabanı seçimi

### SQLite (varsayılan — kurulum gerektirmez)

`.env` içinde:

```env
DB_ENGINE=sqlite
DB_NAME=restaurant
```

Tek dosyalı veritabanı `D:\Restaurant\restaurant.sqlite3` olarak oluşturulur.
Tek şubeli, 1-3 terminalli kullanım için yeterlidir. WAL modu etkindir, bu
sayede POS ve mutfak ekranı aynı anda yazabilir.

### PostgreSQL (çok terminalli / üretim)

1. [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
   adresinden kurun.
2. Veritabanı ve kullanıcı oluşturun:

   ```sql
   CREATE DATABASE restaurant;
   CREATE USER restaurant WITH PASSWORD 'guclu-bir-parola';
   GRANT ALL PRIVILEGES ON DATABASE restaurant TO restaurant;
   ```

3. Sürücüyü kurun:

   ```powershell
   pip install "psycopg[binary]"
   ```

4. `.env` dosyasını güncelleyin:

   ```env
   DB_ENGINE=postgres
   DB_NAME=restaurant
   DB_USER=restaurant
   DB_PASSWORD=guclu-bir-parola
   DB_HOST=127.0.0.1
   DB_PORT=5432
   ```

5. Tabloları oluşturun:

   ```powershell
   python manage.py migrate
   ```

---

## 6. Ağdaki diğer cihazlardan erişim

Mutfak ekranını tablete, POS'u başka bir bilgisayara açmak için:

1. Sunucu bilgisayarın yerel IP adresini öğrenin:

   ```powershell
   ipconfig | Select-String "IPv4"
   ```

   Örnek: `192.168.1.42`

2. `.env` dosyasını güncelleyin:

   ```env
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.42
   DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://192.168.1.42:8000
   ```

3. Sunucuyu tüm arayüzlerde dinletin:

   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```

4. Windows Güvenlik Duvarı'nda 8000 portuna izin verin:

   ```powershell
   # Yönetici olarak çalıştırılan PowerShell'de:
   New-NetFirewallRule -DisplayName "Restaurant POS" -Direction Inbound `
       -LocalPort 8000 -Protocol TCP -Action Allow -Profile Private
   ```

5. Diğer cihazlardan `http://192.168.1.42:8000` adresini açın.

> ⚠️ Bu yapılandırma **yalnızca güvendiğiniz yerel ağ** içindir. Sistemi
> internete açacaksanız mutlaka HTTPS kullanın ve
> [SECURITY.md](SECURITY.md) belgesindeki üretim kontrol listesini uygulayın.

---

## 7. Yerel yapay zekâ (LM Studio)

1. [lmstudio.ai](https://lmstudio.ai) adresinden indirin ve kurun.
2. **Discover** sekmesinden bir model indirin (bkz. [README](README.md#lm-studio-kurulumu-yerel-yapay-zekâ)).
3. **Developer** sekmesi → **Start Server**.
4. Kontrol edin:

   ```powershell
   python manage.py ai_check --provider lmstudio
   ```

Beklenen çıktı:

```
[OK]   LM Studio (yerel)    220 ms
       LM Studio (yerel) erişilebilir (6 model).
       Görev eşlemesi:
         ✓ general      → google/gemma-4-12b-qat
         ✓ reasoning    → qwen/qwen3-vl-8b
         ...
```

Yanında `!` işareti olan model, LM Studio'da yüklü değil demektir. `.env`
dosyasındaki ilgili `LMSTUDIO_MODEL_*` satırını sunucudaki bir modelle
değiştirin.

---

## 8. Windows yardımcı dosyaları

| Dosya | Ne yapar |
|---|---|
| `setup_windows.ps1` | Tam kurulum sihirbazı |
| `run_app.bat` | Uygulamayı başlatır ve tarayıcıyı açar (günlük kullanım) |
| `run_dev.ps1` | Geliştirici sunucusu (otomatik yeniden yükleme, ayrıntılı log) |
| `test_all.ps1` | Tüm testleri ve kalite kontrollerini çalıştırır |
| `backup.ps1` | Veritabanı, medya ve `.env` yedeği alır |
| `restore.ps1` | Yedekten geri yükler |

---

## 9. Sorun giderme

| Belirti | Neden | Çözüm |
|---|---|---|
| `python bulunamadı` | PATH'e eklenmemiş | Python'u "Add to PATH" seçeneğiyle yeniden kurun |
| `Activate.ps1 yüklenemiyor` | Script politikası | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `ModuleNotFoundError: django` | Sanal ortam etkin değil | `.\.venv\Scripts\Activate.ps1` |
| `Port 8000 kullanımda` | Başka bir uygulama portu tutuyor | `python manage.py runserver 8001` |
| `database is locked` | SQLite eşzamanlılık | Sunucuyu yeniden başlatın; kalıcıysa PostgreSQL'e geçin |
| `CSRF verification failed` | Farklı IP'den erişim | `DJANGO_CSRF_TRUSTED_ORIGINS` değerine adresi ekleyin |
| Sayfa stilsiz görünüyor | Statik dosyalar toplanmamış | `python manage.py collectstatic --noinput` |
| Yapay zekâ "erişilemiyor" diyor | LM Studio kapalı | LM Studio → Developer → Start Server |
| AI yanıtı boş dönüyor | Muhakeme modeli token sınırına takıldı | `.env` içinde `AI_MAX_TOKENS=4000` yapın |
| Mutfak ekranı güncellenmiyor | WebSocket bağlanamıyor | Sunucunun `daphne` ile çalıştığını doğrulayın (varsayılan) |
| Değişiklik yaptım ama görünmüyor | Şablon önbelleği | Sunucuyu `--noreload` olmadan başlatın |

### Günlük dosyaları

Hata ayrıntıları için:

```
D:\Restaurant\logs\restaurant.log     — genel uygulama günlüğü
D:\Restaurant\logs\security.log       — giriş denemeleri, yetki olayları
```

Bu dosyalarda API anahtarları ve müşteri kişisel verileri **otomatik olarak
maskelenir**; destek talebine güvenle ekleyebilirsiniz.

---

## 10. Güncelleme

```powershell
cd D:\Restaurant
.\.venv\Scripts\Activate.ps1

# Önce yedek alın
.\backup.ps1

# Yeni sürümü çekin (git kullanıyorsanız)
git pull

# Bağımlılıkları ve veritabanını güncelleyin
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput

# Testleri çalıştırın
python -m pytest -q
```

---

## 11. Kaldırma

Sistem **kayıt defterine yazmaz ve sistem dosyası değiştirmez.** Kaldırmak için:

1. Sunucuyu durdurun (`Ctrl+C`).
2. Yedek alın: `.\backup.ps1`
3. `D:\Restaurant` klasörünü silin.

Python ve LM Studio ayrı programlardır; Denetim Masası'ndan kaldırılır.
