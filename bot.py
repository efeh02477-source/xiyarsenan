import discord
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env")

try:
    FORUM_KANAL_ID = int(os.getenv('FORUM_KANAL_ID', 0))
except ValueError:
    print("Hata: FORUM_KANAL_ID sayı olmalıdır.")
    sys.exit(1)

FORUM_KANAL_ADI = "dm-kutusu"


class GuvenliBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # kullanici_id -> thread_id
        self.kullanici_thread_haritasi = {}
        # thread_id -> kullanici_id
        self.thread_kullanici_haritasi = {}

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="İO|Sunucu Yönetimi Merkezi"
        ))
        print(f'Sistem kontrol edildi. {self.user} aktif!')

    # ──────────────────────────────────────────
    # Yardımcı: Forum kanalını al ya da oluştur
    # ──────────────────────────────────────────
    async def _forum_kanal_al_veya_olustur(self):
        global FORUM_KANAL_ID

        if FORUM_KANAL_ID != 0:
            kanal = self.get_channel(FORUM_KANAL_ID)
            if kanal:
                return kanal
            try:
                kanal = await self.fetch_channel(FORUM_KANAL_ID)
                return kanal
            except Exception:
                pass

        guild = next(iter(self.guilds), None)
        if guild is None:
            print("❌ Bot hiçbir sunucuda değil.")
            return None

        for kanal in guild.forums:
            if kanal.name == FORUM_KANAL_ADI:
                FORUM_KANAL_ID = kanal.id
                self._env_guncelle("FORUM_KANAL_ID", kanal.id)
                print(f"✅ Forum kanalı bulundu: #{kanal.name} ({kanal.id})")
                return kanal

        try:
            yeni_kanal = await guild.create_forum(
                name=FORUM_KANAL_ADI,
                topic="📩 Kullanıcıların bot üzerinden gönderdiği DM mesajları.",
                reason="DM Forum Sistemi — otomatik oluşturuldu."
            )
            FORUM_KANAL_ID = yeni_kanal.id
            self._env_guncelle("FORUM_KANAL_ID", yeni_kanal.id)
            print(f"✅ Forum kanalı oluşturuldu: #{yeni_kanal.name} ({yeni_kanal.id})")
            return yeni_kanal
        except discord.Forbidden:
            print("❌ Botun 'Kanal Yönet' yetkisi yok.")
            return None
        except Exception as e:
            print(f"❌ Forum kanalı oluşturma hatası: {e}")
            return None

    def _env_guncelle(self, anahtar: str, deger):
        env_yolu = ".env"
        satir = f"{anahtar}={deger}\n"
        satirlar = []

        if os.path.exists(env_yolu):
            with open(env_yolu, "r", encoding="utf-8") as f:
                satirlar = f.readlines()

        guncellendi = False
        for i, s in enumerate(satirlar):
            if s.startswith(f"{anahtar}="):
                satirlar[i] = satir
                guncellendi = True
                break

        if not guncellendi:
            satirlar.append(satir)

        with open(env_yolu, "w", encoding="utf-8") as f:
            f.writelines(satirlar)
        print(f"💾 .env güncellendi: {anahtar}={deger}")

    # ──────────────────────────────────────────
    # Mesaj yönlendirme
    # ──────────────────────────────────────────
    async def on_message(self, message):
        if message.author == self.user:
            return

        # Kullanıcıdan gelen DM
        if isinstance(message.channel, discord.DMChannel):
            await self._dm_isle(message)
            return

        # Forum thread'inden cevap → kullanıcının DM'ine
        if (
            isinstance(message.channel, discord.Thread)
            and FORUM_KANAL_ID != 0
            and message.channel.parent_id == FORUM_KANAL_ID
            and message.channel.id in self.thread_kullanici_haritasi
        ):
            await self._forum_reply_isle(message)

    # ──────────────────────────────────────────
    # DM → Forum Thread
    # ──────────────────────────────────────────
    async def _dm_isle(self, message):
        try:
            forum_channel = await self._forum_kanal_al_veya_olustur()
            if forum_channel is None:
                return

            icerik = message.clean_content[:1000] if message.content else ""

            gorsel_linkleri = "\n".join(
                att.url for att in message.attachments
                if att.content_type and att.content_type.startswith('image')
            )

            thread_mesaji = f"📩 **Yeni DM**\n👤 {message.author.mention} (`{message.author}`) — ID: `{message.author.id}`"
            if icerik:
                thread_mesaji += f"\n\n{icerik}"
            if gorsel_linkleri:
                thread_mesaji += f"\n{gorsel_linkleri}"
            thread_mesaji += "\n\n*Bu thread'e yazarak cevap verebilirsiniz.*"

            kullanici_id = message.author.id

            # Mevcut açık thread var mı?
            if kullanici_id in self.kullanici_thread_haritasi:
                thread_id = self.kullanici_thread_haritasi[kullanici_id]
                try:
                    thread = self.get_channel(thread_id) or await self.fetch_channel(thread_id)
                    if thread.archived:
                        await thread.edit(archived=False)
                    await thread.send(thread_mesaji)
                    await message.add_reaction('✅')
                    return
                except Exception:
                    pass  # Thread bulunamazsa yenisini aç

            # Yeni thread oluştur
            thread_adi = f"💬 {message.author.display_name} ({message.author.id})"[:100]
            yeni_thread = await forum_channel.create_thread(
                name=thread_adi,
                content=thread_mesaji,
                reason=f"DM bildirimi: {message.author}"
            )
            thread = yeni_thread.thread

            self.kullanici_thread_haritasi[kullanici_id] = thread.id
            self.thread_kullanici_haritasi[thread.id] = kullanici_id

            await message.add_reaction('✅')

        except discord.Forbidden:
            print("Hata: Forum kanalına erişim yetkisi yok.")
        except Exception as e:
            print(f"DM işleme hatası: {e}")

    # ──────────────────────────────────────────
    # Forum Thread yanıtı → Kullanıcıya DM
    # ──────────────────────────────────────────
    async def _forum_reply_isle(self, message):
        try:
            hedef_kullanici_id = self.thread_kullanici_haritasi[message.channel.id]
            hedef_kullanici = self.get_user(hedef_kullanici_id) or await self.fetch_user(hedef_kullanici_id)

            if hedef_kullanici is None:
                await message.channel.send("❌ Hedef kullanıcı bulunamadı.", delete_after=5)
                return

            icerik = message.clean_content[:1000] if message.content else ""

            gorsel_linkleri = "\n".join(
                att.url for att in message.attachments
                if att.content_type and att.content_type.startswith('image')
            )

            dm_mesaji = "📬 **Sunucudan Mesaj**"
            if icerik:
                dm_mesaji += f"\n\n{icerik}"
            if gorsel_linkleri:
                dm_mesaji += f"\n{gorsel_linkleri}"

            await hedef_kullanici.send(dm_mesaji)
            await message.add_reaction('✅')

        except discord.Forbidden:
            await message.channel.send(
                "❌ Kullanıcının DM'i kapalı, mesaj gönderilemedi.", delete_after=7
            )
        except Exception as e:
            print(f"Forum reply işleme hatası: {e}")


if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True

    client = GuvenliBot(intents=intents)

    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("Hata: .env dosyasında DISCORD_TOKEN bulunamadı!")
    else:
        client.run(token)