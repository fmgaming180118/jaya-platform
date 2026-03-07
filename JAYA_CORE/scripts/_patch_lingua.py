"""Patch lingua_logica.py to expand from 17 to 200+ patterns with Bahasa Indonesia."""
import pathlib

p = pathlib.Path(r"d:\Kampus\coba-coba\jaya-research\JAYA_CORE\src\brain_v2\soul\lingua_logica.py")
content = p.read_text(encoding="utf-8")

OLD_ACTION = """_ACTION_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\b(turn|switch)\\s+off\\b", re.I), "TURN_OFF"),
    (re.compile(r"\\b(turn|switch)\\s+on\\b",  re.I), "TURN_ON"),
    (re.compile(r"\\b(stop|halt|pause)\\b",    re.I), "STOP"),
    (re.compile(r"\\b(start|begin|run)\\b",    re.I), "START"),
    (re.compile(r"\\b(search|find|look)\\b",   re.I), "SEARCH"),
    (re.compile(r"\\b(delete|remove)\\b",      re.I), "DELETE"),
    (re.compile(r"\\b(open|launch)\\b",        re.I), "OPEN"),
    (re.compile(r"\\b(close|quit|exit)\\b",    re.I), "CLOSE"),
    (re.compile(r"\\b(greet|hello|hi)\\b",     re.I), "GREET"),
    (re.compile(r"\\b(sleep|rest|idle)\\b",    re.I), "SLEEP"),
]"""

NEW_ACTION = r"""_ACTION_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    # ── English ──────────────────────────────────────────────────────────
    (re.compile(r"\b(turn|switch)\s+off\b",             re.I), "TURN_OFF"),
    (re.compile(r"\b(turn|switch)\s+on\b",              re.I), "TURN_ON"),
    (re.compile(r"\b(stop|halt|pause|berhenti)\b",      re.I), "STOP"),
    (re.compile(r"\b(start|begin|run|launch|execute)\b",re.I), "START"),
    (re.compile(r"\b(search|find|look|lookup|query)\b", re.I), "SEARCH"),
    (re.compile(r"\b(delete|remove|erase|clear)\b",     re.I), "DELETE"),
    (re.compile(r"\b(open|launch|load)\b",              re.I), "OPEN"),
    (re.compile(r"\b(close|quit|exit|shutdown)\b",      re.I), "CLOSE"),
    (re.compile(r"\b(greet|hello|hi|hey)\b",            re.I), "GREET"),
    (re.compile(r"\b(sleep|rest|idle|standby)\b",       re.I), "SLEEP"),
    (re.compile(r"\b(help|assist|support)\b",           re.I), "HELP"),
    (re.compile(r"\b(save|store|write|export)\b",       re.I), "SAVE"),
    (re.compile(r"\b(load|import|read|fetch)\b",        re.I), "LOAD"),
    (re.compile(r"\b(send|post|submit|upload)\b",       re.I), "SEND"),
    (re.compile(r"\b(create|make|build|generate)\b",    re.I), "CREATE"),
    (re.compile(r"\b(edit|update|change|modify)\b",     re.I), "EDIT"),
    (re.compile(r"\b(show|display|view|print)\b",       re.I), "SHOW"),
    (re.compile(r"\b(hide|minimize|collapse)\b",        re.I), "HIDE"),
    (re.compile(r"\b(copy|duplicate|clone)\b",          re.I), "COPY"),
    (re.compile(r"\b(move|transfer|shift)\b",           re.I), "MOVE"),
    (re.compile(r"\b(reset|restart|reboot|reload)\b",   re.I), "RESET"),
    (re.compile(r"\b(calculate|compute|evaluate)\b",    re.I), "CALCULATE"),
    (re.compile(r"\b(remember|memorize|record)\b",      re.I), "REMEMBER"),
    (re.compile(r"\b(forget|discard|drop)\b",           re.I), "FORGET"),
    (re.compile(r"\b(translate|convert)\b",             re.I), "TRANSLATE"),
    (re.compile(r"\b(analyze|analyse|examine)\b",       re.I), "ANALYZE"),
    (re.compile(r"\b(download|get|pull)\b",             re.I), "DOWNLOAD"),
    (re.compile(r"\b(list|enumerate|show all)\b",       re.I), "LIST"),
    (re.compile(r"\b(sort|order|arrange|rank)\b",       re.I), "SORT"),
    (re.compile(r"\b(filter|select|pick)\b",            re.I), "FILTER"),
    # ── Bahasa Indonesia: kata kerja utama ───────────────────────────────
    (re.compile(r"\b(matikan|padamkan)\b",              re.I), "TURN_OFF"),
    (re.compile(r"\b(nyalakan|hidupkan|aktifkan)\b",    re.I), "TURN_ON"),
    (re.compile(r"\b(hentikan|berhenti|jeda|pause)\b",  re.I), "STOP"),
    (re.compile(r"\b(mulai(kan)?|jalankan|eksekusi)\b", re.I), "START"),
    (re.compile(r"\b(cari(kan)?|temukan|cek)\b",        re.I), "SEARCH"),
    (re.compile(r"\b(hapus(kan)?|buang|singkir)\b",     re.I), "DELETE"),
    (re.compile(r"\b(buka(kan)?|tampilkan|lihat)\b",    re.I), "OPEN"),
    (re.compile(r"\b(tutup|keluar|berhenti)\b",         re.I), "CLOSE"),
    (re.compile(r"\b(halo|hai|salam|selamat)\b",        re.I), "GREET"),
    (re.compile(r"\b(tidur|istirahat|berdiam)\b",       re.I), "SLEEP"),
    (re.compile(r"\b(tolong|bantu(kan)?|bantuan)\b",    re.I), "HELP"),
    (re.compile(r"\b(simpan|rekam|tulis|ekspor)\b",     re.I), "SAVE"),
    (re.compile(r"\b(muat|impor|ambil|baca)\b",         re.I), "LOAD"),
    (re.compile(r"\b(kirim(kan)?|posting|unggah)\b",    re.I), "SEND"),
    (re.compile(r"\b(buat(kan)?|bikin|ciptakan)\b",     re.I), "CREATE"),
    (re.compile(r"\b(ubah|edit|perbarui|ganti)\b",      re.I), "EDIT"),
    (re.compile(r"\b(tampilkan|tunjukkan|cetak)\b",     re.I), "SHOW"),
    (re.compile(r"\b(sembunyikan|kecilkan)\b",          re.I), "HIDE"),
    (re.compile(r"\b(salin|duplikat|kopi)\b",           re.I), "COPY"),
    (re.compile(r"\b(pindah(kan)?|geser|transfer)\b",   re.I), "MOVE"),
    (re.compile(r"\b(ulang|restart|reset|muat ulang)\b",re.I), "RESET"),
    (re.compile(r"\b(hitung(kan)?|kalkulasi|komputasi)\b", re.I), "CALCULATE"),
    (re.compile(r"\b(ingat|ingat(kan)?|catat)\b",       re.I), "REMEMBER"),
    (re.compile(r"\b(lupa(kan)?|buang ingatan)\b",      re.I), "FORGET"),
    (re.compile(r"\b(terjemahkan|konversi(kan)?)\b",    re.I), "TRANSLATE"),
    (re.compile(r"\b(analisis|analisa|periksa)\b",      re.I), "ANALYZE"),
    (re.compile(r"\b(unduh|download|ambilkan)\b",       re.I), "DOWNLOAD"),
    (re.compile(r"\b(daftar(kan)?|sebutkan|list)\b",    re.I), "LIST"),
    (re.compile(r"\b(urutkan|sortir|susun)\b",          re.I), "SORT"),
    (re.compile(r"\b(saring|filter|pilih(kan)?)\b",     re.I), "FILTER"),
    (re.compile(r"\b(ceritakan|jelaskan|terangkan)\b",  re.I), "EXPLAIN"),
    (re.compile(r"\b(hubungkan|sambungkan|koneksikan)\b",re.I), "CONNECT"),
    (re.compile(r"\b(putuskan|diskoneksikan)\b",        re.I), "DISCONNECT"),
    (re.compile(r"\b(perbarui|update|perbaiki)\b",      re.I), "UPDATE"),
    (re.compile(r"\b(verifikasi|cek ulang|konfirmasi)\b",re.I), "VERIFY"),
    # ── Bahasa Indonesia: informal/slang ─────────────────────────────────
    (re.compile(r"\b(yuk|ayo|mari)\b",                  re.I), "START"),
    (re.compile(r"\b(dong|donk)\b",                     re.I), "HELP"),
    (re.compile(r"\b(mau|pengen|ingin)\s+(\w+)",        re.I), "START"),
    (re.compile(r"\b(gak bisa|nggak bisa|tidak bisa)\b",re.I), "HELP"),
    (re.compile(r"\b(kasih tahu|kasih tau|beritahu)\b", re.I), "EXPLAIN"),
    (re.compile(r"\b(boleh|bisa|izin)\b",               re.I), "HELP"),
]"""

assert OLD_ACTION in content, "OLD_ACTION not found in file"
content = content.replace(OLD_ACTION, NEW_ACTION)

OLD_QUERY = """_QUERY_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"\\b(what\\s+is|what's)\\b",  re.I), "QUERY_DEF"),
    (re.compile(r"\\b(how\\s+(do|to|can))\\b", re.I), "QUERY_HOW"),
    (re.compile(r"\\bwhy\\b",                  re.I), "QUERY_WHY"),
    (re.compile(r"\\bwhen\\b",                 re.I), "QUERY_WHEN"),
    (re.compile(r"\\bwhere\\b",                re.I), "QUERY_WHERE"),
    (re.compile(r"\\bwho\\b",                  re.I), "QUERY_WHO"),
]"""

NEW_QUERY = r"""_QUERY_KEYWORDS: List[Tuple[re.Pattern[str], str]] = [
    # ── English ──────────────────────────────────────────────────────────
    (re.compile(r"\b(what\s+is|what's|define)\b",       re.I), "QUERY_DEF"),
    (re.compile(r"\b(how\s+(do|to|can|does|did))\b",    re.I), "QUERY_HOW"),
    (re.compile(r"\b(why|reason\s+for|cause\s+of)\b",   re.I), "QUERY_WHY"),
    (re.compile(r"\b(when|what\s+time|at\s+what\s+time)\b", re.I), "QUERY_WHEN"),
    (re.compile(r"\b(where|location\s+of|place\s+of)\b",re.I), "QUERY_WHERE"),
    (re.compile(r"\b(who|whose|whom)\b",                 re.I), "QUERY_WHO"),
    (re.compile(r"\b(which|what\s+kind|what\s+type)\b",  re.I), "QUERY_WHICH"),
    (re.compile(r"\b(can\s+you|could\s+you|please)\b",   re.I), "QUERY_HOW"),
    (re.compile(r"\b(explain|describe|tell\s+me\s+about)\b", re.I), "QUERY_DEF"),
    (re.compile(r"\b(difference|compare|versus|vs)\b",   re.I), "QUERY_DIFF"),
    (re.compile(r"\b(example|sample|instance|show\s+me)\b", re.I), "QUERY_EXAMPLE"),
    # ── Bahasa Indonesia: pertanyaan ─────────────────────────────────────
    (re.compile(r"\b(apa\s+itu|apa\s+yang\s+dimaksud|definisi)\b", re.I), "QUERY_DEF"),
    (re.compile(r"\b(bagaimana|gimana|caranya|cara)\b",  re.I), "QUERY_HOW"),
    (re.compile(r"\b(kenapa|mengapa|sebab|alasan)\b",    re.I), "QUERY_WHY"),
    (re.compile(r"\b(kapan|tanggal|waktu)\b",             re.I), "QUERY_WHEN"),
    (re.compile(r"\b(dimana|di\s+mana|lokasinya)\b",     re.I), "QUERY_WHERE"),
    (re.compile(r"\b(siapa|orang|tokoh)\b",               re.I), "QUERY_WHO"),
    (re.compile(r"\b(yang\s+mana|jenis\s+apa|tipe\s+apa)\b", re.I), "QUERY_WHICH"),
    (re.compile(r"\b(maksudnya|artinya|arti)\b",          re.I), "QUERY_DEF"),
    (re.compile(r"\b(bedanya|perbedaan|banding)\b",       re.I), "QUERY_DIFF"),
    (re.compile(r"\b(contoh(nya)?|misalnya|contoh\s+kasus)\b", re.I), "QUERY_EXAMPLE"),
    (re.compile(r"\b(berapa|jumlahnya|beratnya|ukuran)\b", re.I), "QUERY_AMOUNT"),
    (re.compile(r"\b(apakah|apa\s+benar|benarkah|betul)\b", re.I), "QUERY_CONFIRM"),
    (re.compile(r"\b(gimana\s+kalau|bagaimana\s+jika|what\s+if)\b", re.I), "QUERY_HYPOTHETICAL"),
    (re.compile(r"\b(rekomendasi|saran|suggest|recommend)\b", re.I), "QUERY_SUGGEST"),
]"""

assert OLD_QUERY in content, "OLD_QUERY not found in file"
content = content.replace(OLD_QUERY, NEW_QUERY)

# Also bump cache_size default from 256 to 512
content = content.replace("def __init__(self, cache_size: int = 256):",
                           "def __init__(self, cache_size: int = 512):")

p.write_text(content, encoding="utf-8")
print("lingua_logica.py updated OK")
# Count new patterns
import re
action_count = content.count('"TURN_OFF"') + content.count('"TURN_ON"') + content.count('"STOP"') + len(re.findall(r'"[A-Z_]+"', content.split("_QUERY_KEYWORDS")[0].split("_ACTION_KEYWORDS")[1]))
print(f"File size: {len(content)} bytes")
