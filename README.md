# Jarvis

Kişisel asistan. Yazarak komut verilir. Veriler yalnızca bu bilgisayarda, `data/jarvis.db` içinde durur.

> **Hobi projesi.** Windows'ta denendi, bakımı ve desteği garanti edilmez. Kendi API anahtarın ve kendi Google/GitHub hesabınla kurulur; depoda hiçbir anahtar yoktur. Gmail ve Takvim bağlantıları yalnızca okuma yetkisiyle çalışır. Gemini ücretsiz katmanında gönderilen içerik Google tarafından ürün geliştirmede kullanılabilir, hassas bilgi göndermeyin.

## Sohbet arayüzü (önerilen)

`jarvis-baslat.bat` dosyasına çift tıkla. Tarayıcıda `http://localhost:8765` açılır.

İlk açılışta ücretsiz Gemini API anahtarı ister:
1. https://aistudio.google.com/apikey adresini aç, Google hesabınla giriş yap.
2. **Create API key** düğmesine bas, anahtarı kopyala.
3. Sayfadaki kutuya yapıştır. Anahtar doğrulanır ve yalnızca bu bilgisayarda `.env` dosyasına yazılır.

Model varsayılan olarak `gemini-2.5-flash` (ölçümde ~1 sn; `gemini-3.8-flash` aynı gün 90 sn zaman aşımı verdi). Değiştirmek için `.env` içine `JARVIS_MODEL=...` yaz.

**Gizlilik:** Gemini ücretsiz katmanında gönderdiğin metin ve fotoğraflar Google tarafından ürün geliştirmek için kullanılabilir. Parola, kimlik, banka numarası gibi hassas şeyler yazma. Fotoğraflar tarayıcıda küçültülüp yeniden kodlanır (konum bilgisi silinir).

**Güvenlik:** Sunucu yalnızca bu bilgisayardan erişilebilir (127.0.0.1). Yapay zekanın dosya taşıma, silme ya da mail gönderme aracı yoktur. İndirilenler yalnızca önizlenir; taşıma sadece sayfadaki "Evet, taşı" düğmesiyle olur ve geri alınabilir.

## Gmail ve Takvim'i bağlama (salt okunur)

Tek seferlik kurulum, yaklaşık 10 dakika:
1. https://console.cloud.google.com adresine git, bir proje oluştur (örn. "jarvis").
2. **APIs & Services > Library**'de **Gmail API** ve **Google Calendar API**'yi bul, ikisini de **Enable** et.
3. **Google Auth platform** (eski adıyla OAuth consent screen) bölümünü kur: uygulama adı "Jarvis", kullanıcı türü **External**, iletişim e-postası kendin. **Audience** bölümünde **Test users** listesine kendi Gmail adresini ekle.
4. **Google Auth platform > Clients > Create client**: **Application type = Desktop app**, bir ad ver, **Create**.
5. Açılan pencereden **Download JSON** ile dosyayı indir ve **jarvis klasörüne** koy (adı `client_secret_...json` ya da `credentials.json` kalabilir).
6. Jarvis'te **Bağlantılar > Google'ı bağla**'ya bas, açılan sekmede izin ver. "Google bu uygulamayı doğrulamadı" uyarısı çıkar (uygulama sana ait ve test modunda): **Gelişmiş > devam** de. İki izni de işaretle.

İstenen izinler yalnızca okumadır (`gmail.readonly`, `calendar.events.readonly`). Test modundaki uygulamalarda Google bağlantıyı yaklaşık 7 günde bir geçersiz kılabilir; Jarvis bunu söyler, **Yeniden bağla** yeterli.

## GitHub'ı bağlama (salt okunur)

1. GitHub > profil resmi > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. Ad ver, süre seç (örn. 90 gün), **Repository access**'ten istediğin repoları seç.
3. **Permissions** altında **Issues: Read-only** ve **Pull requests: Read-only** ver (Metadata otomatik gelir). Başka hiçbir izin verme.
4. Token'ı **Bağlantılar > GitHub** kutusuna yapıştır. Kaydetmeden önce doğrulanır.

Not: ince ayarlı token'larla GitHub bildirimleri (notifications) okunamayabilir; bu yüzden Jarvis inceleme bekleyen PR'ları, açık PR'larını ve sana atanan issue'ları arar.

## Hava durumu

**Bağlantılar > Şehir** kutusuna şehrini yaz (ücretsiz Open-Meteo, anahtar gerekmez).

## Komut satırı

```
uv run --no-project --python 3.13 python -m jarvis.cli <komut>
```

(PYTHONPATH proje klasörü olmalı. Sonraki aşamada `jarvis` komutu olarak kurulacak.)

| Komut | Örnek |
|---|---|
| not | `not ekle CV'yi güncelle` · `not liste` |
| hatırlatıcı | `hatirlat ekle -w "yarın 18:30" Mail cevapla` · `hatirlat liste` · `hatirlat bitti --id 1` |
| harcama | `harcama ekle 125.5 market migros` · `harcama ozet` |
| kayıt | `kayit su 500` · `kayit uyku 7.5` · `kayit spor 30 koşu` · `kayit kalori 620 tavuk pilav` · `kayit kilo 78` |
| hedef | `hedef ekle Haftada 5 saat Python` · `hedef liste` · `hedef bitti --id 1` |
| özet | `bugun` · `hafta` |
| İndirilenler | `organize` (kuru çalıştırma) · `organize --apply` · `organize --undo` |

Zaman biçimleri: `yarın 09:30`, `bugün 18:00`, `2026-11-01 08:00`, `+3g`, `+2s`.

## Güvenlik ilkeleri
- Hiçbir şey silinmez. Dosya düzenleyici yalnızca taşır, kuru çalıştırma varsayılandır, geri alınabilir.
- Son 1 saatte inen ve hâlâ inmekte olan dosyalara dokunulmaz.
- Mail gönderme, takvime yazma gibi geri alınamaz işler (sonraki aşamalar) her zaman önce onay ister.
- Anahtar ve token dosyaları `.gitignore` içinde.

## Yol haritası
1. **Çekirdek** (bitti): not, hatırlatıcı, harcama, sağlık kaydı, hedefler, özetler, dosya düzeni.
2. **Sohbet arayüzü**: doğal dille komut (Telegram botu ya da yerel web sayfası) + ücretsiz yapay zeka.
3. **Kalori**: yemek fotoğrafı → görsel model tahmini → kayıt.
4. **Google**: Gmail (okuma, triyaj, taslak) ve Takvim, önce yalnızca okuma izniyle.
5. **GitHub**: bildirim, PR/issue özeti.
6. **Sabah brifingi**: takvim + mail + GitHub + hava + üç öncelik.
7. **Kariyer**: CV'yi ilana uyarlama, LinkedIn taslakları (LinkedIn'e otomasyon yok, taslağı sen yayınlarsın).
