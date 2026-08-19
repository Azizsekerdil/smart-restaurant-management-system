# Yol Haritası

Planlanan geliştirmeler, öncelik sırasıyla. Tarihler taahhüt değil, tahmindir.

---

## v1.1 — Mali mevzuat ve donanım

Sistemin Türkiye'de tam yasal uyumla kullanılabilmesi için gereken adımlar.

| Konu | Açıklama |
|---|---|
| **ÖKC entegrasyonu** | Onaylı yeni nesil yazarkasa ile haberleşme; yasal Z raporu ve mali fiş üretimi. Cihaz üreticisinin SDK'sı gerekir. |
| **e-Fatura / e-Arşiv** | Yetkili özel entegratör (ör. Foriba, Uyumsoft, Logo) API'si ile fatura üretimi ve GİB'e iletim. |
| **Termal yazıcı sürücüsü** | ESC/POS protokolü ile doğrudan yazdırma; şu an tarayıcı yazdırma diyaloğu kullanılıyor. |
| **Kasa çekmecesi** | Yazıcı üzerinden çekmece açma sinyali. |
| **Barkod okuyucu** | Ürün ve malzeme girişinde barkod desteği (klavye emülasyonu zaten çalışır, özel işleyici eklenecek). |

> **Not:** ÖKC ve e-Fatura entegrasyonları yasal onay ve ticari anlaşma
> gerektirir. Bu nedenle çekirdek projeye değil, ayrı bir eklenti paketine
> alınması değerlendiriliyor.

---

## v1.2 — Ödeme ve teslimat

| Konu | Açıklama |
|---|---|
| **POS terminal entegrasyonu** | Kart ödemesinin cihazdan otomatik okunması (Ingenico, Verifone). |
| **Online ödeme** | iyzico / PayTR ile QR menüden ödeme. |
| **Teslimat platformları** | Yemeksepeti, Getir, Trendyol Yemek siparişlerinin otomatik içe aktarımı. |
| **Kurye takibi** | Harita üzerinde canlı konum ve teslimat süresi tahmini. |
| **Müşteri sipariş takibi** | Müşterinin siparişini QR ile takip edebilmesi. |

---

## v1.3 — Çok şubeli işletme

| Konu | Açıklama |
|---|---|
| **Şube yönetimi** | Tek kurulumda birden fazla şube; şubeler arası yetki ayrımı. |
| **Merkezi menü** | Menü ve fiyatların merkezden yönetilip şubelere dağıtılması. |
| **Şubeler arası transfer** | Malzeme transferi ve merkezi depo. |
| **Konsolide raporlama** | Şube karşılaştırmalı analiz. |
| **Merkezi satın alma** | Toplu sipariş ve tedarikçi anlaşmaları. |

---

## v1.4 — Yapay zekâ derinleştirme

| Konu | Açıklama |
|---|---|
| **Vektör arama (RAG)** | Gömme modeliyle geçmiş sipariş ve yorumlarda anlamsal arama. |
| **Fiş/fatura okuma** | Tedarikçi faturasının görselden okunup satın alma kaydına dönüştürülmesi (görsel model altyapısı hazır). |
| **Sesli sipariş** | Konuşmadan metne dönüşümle sipariş alma. |
| **Gelişmiş tahmin** | Hava durumu, resmî tatil ve yerel etkinlik verilerinin talep tahminine katılması. |
| **Otomatik reçete çıkarımı** | Ürün fotoğrafından malzeme önerisi. |
| **Kişiselleştirilmiş öneri** | Müşteri geçmişine göre ürün önerisi (KVKK rızasına bağlı). |
| **AI eylem onayı** | Asistanın yalnızca yorum değil, onaylı eylem de yapabilmesi (ör. "bu ürünü satışa kapat"). |

---

## v1.5 — Operasyonel derinlik

| Konu | Açıklama |
|---|---|
| **Mobil uygulama** | Garson için PWA veya native uygulama; masa başında sipariş. |
| **Müşteri self-servis** | QR menüden doğrudan sipariş verme. |
| **Gelişmiş vardiya** | Personel tercihleri ve yasal kurallara göre otomatik vardiya oluşturma. |
| **Maliyet muhasebesi** | Sabit/değişken gider dağıtımı, başabaş noktası analizi. |
| **Bütçe ve hedef** | Aylık ciro hedefi ve gerçekleşme takibi. |
| **Menü A/B testi** | Fiyat ve konumlandırma denemelerinin ölçümü. |

---

## Teknik borç ve iyileştirmeler

Şu an bilinen sınırlar ve planlanan çözümleri:

| Konu | Mevcut durum | Planlanan |
|---|---|---|
| Hız sınırlama | Süreç içi bellek | Redis tabanlı, çok işçili uyumlu |
| Kanal katmanı | `InMemoryChannelLayer` varsayılan | Redis'i üretimde varsayılan yapmak |
| CSP | `unsafe-inline` içeriyor (Alpine.js) | Nonce tabanlı CSP |
| Tip denetimi | Kademeli, `mypy` CI'da zorunlu değil | `disallow_untyped_defs` aşamalı açma |
| Uçtan uca test | Yok | Playwright ile kritik akışların E2E testi |
| Dil desteği | Türkçe tam, İngilizce altyapı hazır | `.po` çevirilerinin tamamlanması |
| Erişilebilirlik | Temel (odak, kontrast, kısayol) | WCAG 2.1 AA denetimi |
| Yük testi | Yok | Locust ile POS ve KDS yük profili |
| API belgeleri | Kod içinde | OpenAPI şeması + Swagger UI |

---

## Katkıda bulunma

Bu listedeki bir maddeyi geliştirmek isterseniz önce bir **issue** açıp
yaklaşımınızı paylaşın. Böylece aynı işi iki kişinin yapması önlenir.

Listede olmayan bir fikriniz varsa da issue açabilirsiniz — özellikle
gerçek bir restoran işletiyorsanız, sahadan gelen geri bildirim en değerlisidir.
