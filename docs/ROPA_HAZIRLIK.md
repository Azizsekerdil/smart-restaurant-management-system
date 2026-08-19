# İşleme Faaliyetleri Envanteri Hazırlığı (ROPA / VERBİS Hazırlık)

> Tarih: 2026-08-18 · Durum: **HAZIRLIK** — bu belge resmî bir VERBİS kaydı
> veya GDPR m.30 ROPA beyanı DEĞİLDİR. Veri sorumlusu (işletme sahibi) ve
> varsa DPO/hukuk danışmanı tarafından doldurulup doğrulanmalıdır.
> Köşeli ayraçlı alanlar işletmeye özgüdür.
>
> Makine-okunur alan envanteri: `docs/data_inventory.json` (CI ile kodla
> senkron tutulur). Saklama mekanizması: `manage.py purge_expired_logs`.

## Veri sorumlusu

- Unvan: `[İŞLETME UNVANI]`
- Adres: `[ADRES]`
- İrtibat kişisi: `[AD SOYAD / ROL]`
- VERBİS yükümlülüğü: `[DPO/danışman değerlendirmesi — çalışan sayısı ve
  mali tablo eşiklerine göre]`

## İşleme faaliyetleri

### F-01 Sipariş ve satış (POS)

| Alan | Değer |
|------|-------|
| Amaç | Sipariş alma, adisyon, ödeme, fatura |
| İlgili kişi grubu | Müşteri |
| Veri kategorileri | Kimlik (opsiyonel müşteri kaydı), teslimat adresi/telefonu (paket servis), işlem/finans |
| Hukuki dayanak adayı | Sözleşmenin kurulması/ifası; fatura için hukuki yükümlülük |
| Alıcılar | Mali müşavir `[VARSA]`; başka aktarım yok |
| Yurt dışı aktarım | Yok (yerel kurulumda veri makinede kalır) |
| Saklama | Mali kayıt süreleri `[DPO/mali müşavir]` — envanterde BUSINESS_RECORDS |
| Güvenlik | Rol/izin sistemi, PIN'li yetkili onayı, denetim kaydı, yedek şifreleme uyarısı |

### F-02 Müşteri ilişkisi ve sadakat (CRM)

| Alan | Değer |
|------|-------|
| Amaç | Müşteri tanıma, sadakat puanı, kampanya |
| İlgili kişi grubu | Müşteri |
| Veri kategorileri | Kimlik, iletişim, doğum tarihi (ops.), tercih, **alerji (özel nitelikli aday)**, ziyaret/harcama istatistiği |
| Hukuki dayanak adayı | Sözleşme + pazarlama kanalları için AYRI açık rıza (`ConsentRecord`); alerji için açık rıza adayı |
| Alıcılar | Yok |
| Saklama | Talep üzerine anonimleştirme (`Customer.anonymize`); süreli temizlik DPO kararıyla |
| Güvenlik | `customer.pii` izni olmadan iletişim/alerji maskeli; DSR dışa aktarma denetim kayıtlı |
| İlgili kişi hakları | Erişim/taşınabilirlik: müşteri detay sayfası → "KVKK — veri dosyasını indir"; silme: anonimleştirme akışı |

### F-03 Rezervasyon ve bekleme listesi

- Amaç: masa planlama. Kişi grubu: misafir. Kategoriler: kimlik, iletişim,
  **alerji (özel nitelikli aday)**. Dayanak adayı: sözleşme öncesi talep.
- Saklama: `RETENTION_RESERVATION_GUEST_DAYS` / `RETENTION_WAITLIST_GUEST_DAYS`
  (değer `[DPO]`); sonuçlanmış kayıtlarda misafir bilgisi otomatik redakte edilir.

### F-04 Personel yönetimi (İK)

- Amaç: özlük, vardiya, puantaj, performans. Kişi grubu: çalışan (+ acil
  durum kişisi olarak üçüncü kişi). Kategoriler: kimlik, iletişim, finans
  (ücret), çalışma verisi.
- Dayanak adayı: iş sözleşmesi + İş Kanunu yükümlülükleri.
- Saklama: mevzuat süreleri `[DPO/mali müşavir]`.
- Güvenlik: ücret alanları yalnızca `staff.manage`; performans verisi AI'ya
  yalnızca yerel model şartıyla gider (`AI_SENSITIVE_LOCAL_ONLY`).
- Not: Sistem işe alma/çıkarma/disiplin kararı ÜRETMEZ; AI çıktıları öneri
  düzeyindedir (bkz. HSP_PROJECT_REVIEW.md §2).

### F-05 Güvenlik ve denetim kaydı

- Amaç: hesap güvenliği, hesap verebilirlik. Kategoriler: kullanıcı adı
  anlık görüntüsü, IP, tarayıcı bilgisi.
- Dayanak adayı: meşru menfaat (güvenlik).
- Saklama: `RETENTION_AUDIT_IP_DAYS` (değer `[DPO]`); kayıt gövdesi
  append-only kalır, IP/tarayıcı redakte edilir.

### F-06 Yapay zekâ destekli analiz

- Amaç: işletme analizi (ciro, stok, yorum özeti, tahmin).
- Kategoriler: toplulaştırılmış işletme verisi; müşteri yorum metni;
  personel satış istatistiği.
- Kontroller: tek AI geçidi; PII maskeleme (`AI_MASK_PII`); hassas bağlam
  yalnızca yerel model (`AI_SENSITIVE_LOCAL_ONLY`); sohbet/kullanım kayıtları
  maskeli; bütçe/devre kesici.
- Yurt dışı aktarım: bulut sağlayıcı ETKİNLEŞTİRİLİRSE sağlayıcı bölgesine
  aktarım doğar → sağlayıcı DPA/bölge/saklama şartları `[DPO]` tarafından
  değerlendirilmelidir. Yerel modelde (LM Studio/Ollama) veri makineden çıkmaz.

### F-07 Yedekleme

- Amaç: iş sürekliliği. Kapsam: tüm veritabanı (kişisel veriler dahil).
- Kontroller: yedek indirme ayrı izin; `.env` yedeğe varsayılan girmez;
  fiziksel güvenlik işletme sorumluluğunda (ADMIN_GUIDE §6.5).
- Not: Redaksiyon geçmiş yedek kopyalarını değiştirmez; yedek rotasyonu
  (`BACKUP_KEEP_LAST`) eski kopyaları zamanla eritir.

## Aydınlatma ve rıza

- Aydınlatma metni ve açık rıza AYRI yönetilmelidir (KVKK Kurulu 2026/347
  ilke kararı — kaynak: kvkk.gov.tr). Uygulama rıza kayıtlarını kanal
  bazında tutar; aydınlatma metninin hazırlanması `[DPO/hukuk]` işidir.

## Doğrulama listesi (işletme/DPO)

- [ ] Veri sorumlusu bilgileri dolduruldu
- [ ] VERBİS yükümlülüğü değerlendirildi
- [ ] Saklama süreleri belirlendi ve `.env` RETENTION_* değerlerine girildi
- [ ] Aydınlatma metni hazırlandı ve müşteriye sunuluyor
- [ ] Alerji verisi için açık rıza akışı değerlendirildi
- [ ] Bulut AI kullanılacaksa sağlayıcı DPA/bölge değerlendirmesi yapıldı
