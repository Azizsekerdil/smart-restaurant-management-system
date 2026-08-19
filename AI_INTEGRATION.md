# Yapay Zekâ Entegrasyonu

Bu belge, sistemin yapay zekâ katmanının nasıl tasarlandığını, hangi
sağlayıcılarla çalıştığını, maliyetin nasıl kontrol edildiğini ve gizliliğin
nasıl korunduğunu açıklar.

---

## 1. Temel tasarım ilkesi

> **Sayıyı kod hesaplar, yapay zekâ yalnızca yorumlar.**

Bu, sistemin en önemli tasarım kararıdır. Bir dil modeline "bu ayki ciromu
hesapla" dendiğinde model sayı **uydurabilir**. Bu yüzden:

1. Tüm hesaplar (`ciro`, `marj`, `tükenme tahmini`, `medyan satış`) Python ve
   veritabanı tarafında **deterministik olarak** yapılır.
2. Sonuç JSON olarak modele verilir; modelden yalnızca **yorum ve öneri**
   istenir.
3. İstemler modelden açıkça şunu ister: *"Sana verilen verilerin dışına çıkma,
   sayı uydurma, emin değilsen 'veri yetersiz' de."*

Bunun iki sonucu vardır:

- **Rakamlar her zaman doğrudur** — modelin kalitesinden bağımsızdır.
- **AI erişilemese bile analizler çalışır.** Yanıtta `ai_available: false`
  döner; sayısal kısım ve tablolar yine gösterilir.

---

## 2. Mimari

```
Kullanıcı / Görünüm / API
          │
          ▼
   apps.ai.gateway          ← tek giriş noktası
   ├── mask_pii()           ← KVKK: kişisel veri maskeleme
   ├── build_chain()        ← yönlendirme kararı
   ├── can_use_cloud()      ← bütçe kontrolü
   ├── is_circuit_open()    ← devre kesici
   └── _log()               ← token + maliyet kaydı
          │
          ▼
   apps.ai.providers        ← adapter katmanı
   ├── OpenAICompatibleProvider   (LM Studio, Ollama, NVIDIA, OpenRouter, OpenAI)
   ├── AnthropicProvider          (Claude — Messages API)
   └── GeminiProvider             (Google — generateContent API)
```

Uygulamanın hiçbir yeri sağlayıcıya doğrudan erişmez; her şey `gateway`
üzerinden geçer. Yeni bir sağlayıcı eklemek için tek yapılması gereken
`BaseProvider` arayüzünü uygulayan bir sınıf yazıp `registry.PROVIDER_CLASSES`
içine kaydetmektir.

---

## 3. Desteklenen sağlayıcılar

| Sağlayıcı | Tür | Anahtar gerekir | Varsayılan |
|---|---|---|---|
| **LM Studio** | Yerel | Hayır | ✅ Açık |
| **Ollama** | Yerel | Hayır | Kapalı |
| **NVIDIA NIM** | Bulut | Evet (`nvapi-`) | Kapalı |
| **OpenAI uyumlu** | Bulut | Evet (`sk-`) | Kapalı |
| **Anthropic Claude** | Bulut | Evet | Kapalı |
| **Google Gemini** | Bulut | Evet (`AIza`) | Kapalı |
| **OpenRouter** | Bulut | Evet | Kapalı |

Hiçbiri zorunlu değildir. Hiçbir sağlayıcı yapılandırılmamışsa yapay zekâ
özellikleri kullanıcıya **ne yapması gerektiğini anlatan** bir uyarı gösterir;
uygulamanın kalanı etkilenmez.

### Görev → model eşlemesi

Her sağlayıcı için görev bazlı model tanımlanır. Yönlendirici, çağrının
görevine göre uygun modeli seçer:

| Görev | Ne için kullanılır |
|---|---|
| `general` | Genel asistan, menü açıklaması, günlük özet |
| `reasoning` | Rapor sorgulama, menü mühendisliği, tahmin |
| `code` | AI Geliştirme Merkezi, commit mesajı |
| `math` | Maliyet ve kârlılık analizi |
| `vision` | Fiş/belge görseli okuma |
| `domain` | Alerjen gibi alan bilgisi (yalnızca yardımcı) |
| `embedding` | Vektör gömme (arama/RAG) |

---

## 4. Yönlendirme politikası

`.env` içindeki `AI_ROUTING_POLICY` değeri davranışı belirler:

| Politika | Davranış |
|---|---|
| `local_first` *(varsayılan)* | Önce yerel model; başarısız olursa buluta düşer |
| `local_only` | Yalnızca yerel — **internet gerekmez, veri asla dışarı çıkmaz** |
| `cloud_first` | Önce bulut; başarısız olursa yerele düşer |
| `cloud_only` | Yalnızca bulut |

Politika ne olursa olsun **şu durumlarda zorla yerele düşülür**:

- Çağrı `sensitive=True` ile işaretlendiyse ve `AI_SENSITIVE_LOCAL_ONLY=True` ise
  (ör. müşteri yorumu duygu analizi)
- Günlük veya aylık bütçe dolmuşsa

---

## 5. Dayanıklılık

### Yedekleme (fallback)
Bir sağlayıcı hata verirse zincirdeki sıradaki denenir. Yedek sağlayıcı
kullanıldığında kayıt `outcome=fallback` olarak işaretlenir.

### Yeniden deneme
Geçici hatalarda (zaman aşımı, bağlantı kopması, hız limiti)
`AI_MAX_RETRIES` kadar, artan bekleme süresiyle tekrar denenir.
Yapılandırma hataları (geçersiz anahtar) tekrar denenmez.

### Devre kesici (circuit breaker)
Bir sağlayıcı art arda `CIRCUIT_BREAKER_THRESHOLD` (varsayılan 3) kez
başarısız olursa `CIRCUIT_BREAKER_COOLDOWN_SECONDS` (varsayılan 120 sn)
süreyle zincirden çıkarılır. Böylece kapalı bir LM Studio sunucusu her
istekte 120 saniye beklenmesine yol açmaz.

Devre kesiciler arayüzden sıfırlanabilir:
**Yapay Zekâ → Sağlayıcılar → Devre kesicileri sıfırla**

---

## 6. Maliyet kontrolü

Her çağrı `AIUsageLog` tablosuna kaydedilir: sağlayıcı, model, girdi/çıktı
token sayısı, tahminî maliyet (USD), gecikme, sonuç.

```env
AI_DAILY_BUDGET_USD=1.00      # 0 = limitsiz
AI_MONTHLY_BUDGET_USD=20.00
```

Bütçe dolduğunda:

1. Bulut sağlayıcıları zincirden çıkarılır.
2. Sistem otomatik olarak yerel modele düşer.
3. Yerel model de yoksa kullanıcıya bütçenin dolduğu açıkça bildirilir.

**Yerel modeller ücretsizdir** (`price_per_1m_*` = 0) ve bütçeye yazılmaz.
Bu, "local_first" politikasının hem gizlilik hem de maliyet açısından
varsayılan olmasının nedenidir.

Kullanım ve maliyet: **Yapay Zekâ → Kullanım**

---

## 7. Gizlilik ve KVKK

### İstem maskeleme

`AI_MASK_PII=True` iken, istem sağlayıcıya gönderilmeden önce şu desenler
maskelenir:

| Veri | Maskelenmiş hâli |
|---|---|
| E-posta | `[E-POSTA]` |
| Telefon (TR cep) | `[TELEFON]` |
| T.C. kimlik no | `[TC-KIMLIK]` |
| Kart numarası | `[KART-NO]` |
| IBAN | `[IBAN]` |

### Kayıt maskeleme

`AIUsageLog` içindeki istem ve yanıt önizlemeleri hem PII hem de gizli anahtar
maskelemesinden geçirilir. Aynı filtre uygulama günlüklerine (`logs/*.log`) de
uygulanır.

### Hassas görevler

`sensitive=True` ile işaretlenen çağrılar (müşteri yorumu analizi gibi)
`AI_SENSITIVE_LOCAL_ONLY=True` iken **yalnızca yerel modele** gönderilir.
Yerel model yoksa çağrı yapılmaz ve kullanıcıya nedeni açıklanır.

### API anahtarları

- Yalnızca `.env` dosyasında saklanır — **veritabanına asla yazılmaz**
- Arayüzde maskeli gösterilir (`nvap••••••••••••1f`)
- Günlüklerde otomatik temizlenir
- Güvenli terminalin alt süreçlerine **aktarılmaz** (`_sanitized_env`)
- API yanıtlarında yer almaz (test ile doğrulanır)

---

## 8. Akıllı analizler

| Analiz | Yöntem | Sınırlamalar açıkça belirtilir |
|---|---|---|
| **Menü mühendisliği** | Satış adedi ve marjın medyanına göre 4 grup | Mevsimsellik ve reçetesiz ürünler |
| **Talep tahmini** | Haftanın gününe göre ortalama ± std. sapma | Hava, tatil, etkinlik hesaba katılmaz |
| **Stok tükenme** | Son 30 günün ortalama tüketim hızı | Menü değişikliği etkiler |
| **İsraf analizi** | Nedene ve malzemeye göre maliyet dağılımı | Elle girilen kayıtlara bağlı |
| **Anormallik tespiti** | 2 standart sapma dışındaki değerler | **Kanıt değildir**, her bulguya masum açıklama eklenir |
| **Personel ihtiyacı** | Saatlik yoğunluk / 8 sipariş | Menü karmaşıklığı, yasal mola kuralları |
| **Fiyat simülasyonu** | Varsayılan talep esnekliği | Esneklik **ölçülmemiş**, varsayımdır |
| **Duygu analizi** | LLM sınıflandırması (JSON) | Yerel modele yönlendirilir |

Her analiz sonucu şunları içerir:

- `confidence`: `low` / `medium` / `high` — veri noktası sayısına göre
- `data_points`: analizin dayandığı kayıt sayısı
- `limitations`: neden kesin olmadığının açıklaması

Arayüzde bu bilgiler kullanıcıya **her zaman** gösterilir. Tahminler kesin
gerçek gibi sunulmaz.

---

## 9. Muhakeme (reasoning) modelleri

Bazı modeller yanıt üretmeden önce token harcayarak "düşünür":

- `google/gemma-4-12b-qat` (LM Studio)
- `nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/nemotron-3.5-lightning-30b-a3b` (NVIDIA)

Bu modeller düşünme adımlarını `reasoning_content` alanında döndürür ve nihai
yanıt gelene kadar `content` **boş kalır**. Token sınırı düşükse yanıt hiç
üretilmez.

Sistem bu durumu algılar ve şunu yapar:

1. `content` boş ama `reasoning_content` doluysa ve bitiş nedeni `length` ise
   → açıklayıcı bir hata verir: *"token sınırına düşünme aşamasındayken ulaştı,
   sınırı yükseltin veya muhakeme yapmayan bir model seçin"*
2. Zincirdeki bir sonraki sağlayıcıya geçer.

Varsayılan `AI_MAX_TOKENS=2500` bu modeller için yeterlidir. NVIDIA'nın büyük
muhakeme modellerinde `4000` veya üzeri önerilir.

---

## 10. AI Geliştirme Merkezi

Uygulamanın içinden kod değişikliği önerme özelliği. Güvenlik modeli:

| Katman | Koruma |
|---|---|
| Erişim | Yalnızca `devcenter.access` izni; üretimde varsayılan kapalı |
| Dosya | Yalnızca proje kökü içi; `.env`, veritabanı, `.git`, `media` korumalı |
| Uzantı | Yalnızca `.py .html .css .js .md .txt .json .yml .yaml` |
| Önizleme | Değişiklik **her zaman diff olarak** gösterilir |
| Onay | Kullanıcı onaylamadan hiçbir dosya yazılmaz |
| Yedek | Uygulamadan önce otomatik geri alma noktası |
| Dal | Değişiklik ayrı bir Git dalına uygulanır, ana dala değil |
| Test | Testler çalıştırılmışsa ve başarısızsa **uygulama reddedilir** |
| Geri alma | Tek tıkla önceki dosya durumuna dönüş |

Kod önerisi güçlü bir model gerektirir. Küçük yerel modeller geçerli JSON
üretmekte zorlanabilir; bu durumda sistem anlaşılır bir hata verir ve daha
güçlü bir model önerir.

---

## 11. Güvenli terminal

`apps/devcenter/sandbox.py` içinde 6 katmanlı koruma:

1. **Allowlist** — yalnızca `python, pytest, ruff, black, mypy, bandit, pip,
   npm, npx, git, docker` çalıştırılabilir; bilinmeyen her komut reddedilir
2. **Kabuk yok** — `shell=False`; `&&`, `|`, `;`, `>` yorumlanmaz
3. **Yol hapsi** — proje kökü dışına erişim engellenir, `..` reddedilir
4. **Tehlikeli kalıp reddi** — silme, biçimlendirme, kayıt defteri, kullanıcı
   yönetimi, kimlik bilgisi okuma, ağdan indirme, `git push`,
   `git reset --hard`, `DROP TABLE`, `manage.py flush`
5. **Onay kapısı** — `pip install`, `git commit`, `migrate` gibi yan etkili
   komutlar kullanıcı onayı olmadan çalışmaz
6. **Kayıt ve maskeleme** — her çalıştırma denetim kaydına yazılır, çıktıdaki
   gizli değerler maskelenir, alt sürece API anahtarı aktarılmaz

---

## 12. Test etme

### Komut satırından

```powershell
# Tüm sağlayıcıları test et
python manage.py ai_check

# Tek sağlayıcı + gerçek soru
python manage.py ai_check --provider lmstudio --ask "Merhaba"

# Zaman aşımını uzat (yavaş yerel model)
python manage.py ai_check --provider lmstudio --timeout 120
```

Komut, yapılandırılan görev→model eşlemesini sunucudaki **gerçek model
listesiyle karşılaştırır** ve eşleşmeyenleri `!` ile işaretler.

### Arayüzden

**Yapay Zekâ → Sağlayıcılar → Test et** — bağlantı durumu, gecikme, model
listesi ve eşleme kontrolü gösterilir. API anahtarı hiçbir zaman görüntülenmez.

### REST API

```bash
curl -X POST http://localhost:8000/api/ai/health/ \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=..." \
  -d '{"provider": "lmstudio"}'
```

---

## 13. Testlerin ağa çıkmaması

Test paketi **hiçbir koşulda gerçek bir AI sunucusuna bağlanmaz.**
`config/settings.py` içinde test çalıştırıcısı algılanır ve tüm sağlayıcılar
zorla kapatılır:

```python
_UNDER_TEST = "pytest" in sys.modules or "test" in sys.argv
IS_TEST = DJANGO_ENV == "test" or _UNDER_TEST
```

AI davranışı testlerde sahte (fake) sağlayıcılarla doğrulanır: yönlendirme,
yedekleme, devre kesici, bütçe, maskeleme ve kayıt mantığı gerçek ağ trafiği
olmadan test edilir.

---

## 14. Yeni sağlayıcı ekleme

```python
# apps/ai/providers/benim_saglayicim.py
from apps.ai.providers.base import AIResponse, BaseProvider


class BenimSaglayicim(BaseProvider):
    def chat(self, messages, *, model="", temperature=0.3,
             max_tokens=1500, timeout=120, json_mode=False) -> AIResponse:
        ...
        return AIResponse(text=..., provider=self.key, model=model,
                          input_tokens=..., output_tokens=..., latency_ms=...)

    def list_models(self, *, timeout=15) -> list[str]:
        ...

    def health_check(self, *, timeout=15) -> tuple[bool, str, int]:
        ...
```

Ardından:

1. `apps/ai/providers/registry.py` → `PROVIDER_CLASSES["benim_turum"] = BenimSaglayicim`
2. `config/settings.py` → `AI_PROVIDERS["benim_saglayicim"] = {...}`
3. `.env.example` → yapılandırma satırlarını ekleyin

Arayüz, test ekranı, bütçe takibi ve yönlendirme **otomatik olarak** çalışır.
