"""Minimum authenticated UI/readback modülü.

Yetkiyi UI vermez; yalnız Kernel'de committed gerçek veriyi r54_context_enter
ve r54_*_read üzerinden okuyup sunar. Bellek içi sahte kayıt veya uydurma
LIVE durumu üretmez.
"""
# Modül yüklemede API/önizleme yan etkisi yok; istemci ilgili modülü açıkça alır.
