import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip('"')
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip('"')
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip('"')
last_update_id = 0

# Mapping Koin ke Smart Contract Ethereum (ERC-20)
STATIC_ERC20_MAPPING = {
    "PEPEUSDT": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
    "LINKUSDT": "0x514910771af9ca656af840dff83e8264ecf986ca",
    "SHIBUSDT": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
    "UNIUSDT":  "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
    "AAVEUSDT": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
    "ENAUSDT":  "0x57e114B691Db790C35207b2e685D4A43181e6061",
    "FETUSDT":  "0xaea46A60368A7bD060eec7DF8CBa43b7EF41Cd85",
    "MKRUSDT":  "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
    "LDOUSDT":  "0x5A98FcBEA516Cf06857215779Fd812CA3beF1B32",
    "CRVUSDT":  "0xD533a949740bb3306d119CC777fa900bA034cd52",
}

# Daftar Wallet Bursa Utama (Ethereum) untuk Deteksi Inflow/Outflow
EXCHANGE_WALLETS = {
    "0x28c6c06290cc3f951793910ee5b36e59d909c01b": "Binance Hot Wallet",
    "0x21a31ee1afc51d94c2efccaa2092ad10282715e8": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": "Bybit 1",
    "0xee587ae34da07f5979f4ca3c229340f13a07851a": "Bybit 2",
    "0xa7ef1108d951804f32c914e9f73f27806b72d244": "OKX 1",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX 2",
}

DYNAMIC_MAPPING = {}

def load_dynamic_mapping():
    print("Mencoba menarik data Contract Address dari seluruh koin via CoinGecko...")
    try:
        data = requests.get("https://api.coingecko.com/api/v3/coins/list?include_platform=true").json()
        for coin in data:
            platforms = coin.get('platforms', {})
            sym = coin['symbol'].upper() + "USDT"
            
            # Prioritaskan Ethereum, jika tidak ada cari BSC
            contract = platforms.get('ethereum') or platforms.get('binance-smart-chain')
            
            if contract and sym not in DYNAMIC_MAPPING:
                DYNAMIC_MAPPING[sym] = contract
        print(f"Berhasil! {len(DYNAMIC_MAPPING)} koin (ETH & BSC) kini telah terpetakan secara otomatis.\n")
    except Exception as e:
        print(f"Gagal menarik mapping CoinGecko: {e}. Menggunakan mapping statis...\n")

def send_telegram_message(text, show_button=False):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if show_button:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🔍 Cek Status Bot", "callback_data": "cek_status"}]]
        }
    requests.post(url, json=payload)

def sleep_and_listen(seconds):
    """Pengganti time.sleep() yang sekaligus mendengarkan interaksi tombol Telegram"""
    global last_update_id
    for _ in range(seconds):
        if not TELEGRAM_BOT_TOKEN:
            time.sleep(1)
            continue
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={last_update_id}&timeout=1"
            response = requests.get(url, timeout=2).json()
            if response.get('ok'):
                for update in response['result']:
                    last_update_id = update['update_id'] + 1
                    
                    chat_id = None
                    # Jika tombol ditekan
                    if 'callback_query' in update:
                        chat_id = update['callback_query']['message']['chat']['id']
                        # Beri respon agar loading di tombol hilang
                        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery?callback_query_id={update['callback_query']['id']}")
                    # Jika user mengetik /status
                    elif 'message' in update and 'text' in update['message']:
                        text = update['message']['text'].lower()
                        if '/status' in text or 'status' in text:
                            chat_id = update['message']['chat']['id']
                            
                    if chat_id:
                        msg = "✅ *Status Bot:* Aktif dan Berjalan Sempurna\nRadar Hibrida sedang memantau pasar tanpa hambatan."
                        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
        except:
            time.sleep(1)

def get_onchain_data(api_key, contract_address, current_price, chain_id):
    if not api_key:
        return "No API Key", []
        
    # Menggunakan Endpoint API V2 terbaru
    url = f"https://api.etherscan.io/v2/api?chainid={chain_id}&module=account&action=tokentx&contractaddress={contract_address}&page=1&offset=20&sort=desc&apikey={api_key}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        # Etherscan/BscScan mengembalikan status '0' jika tidak ada transaksi atau ada masalah
        if data['status'] == '0':
            msg = data.get('message', '')
            res = data.get('result', '')
            if "No transactions found" in msg:
                return "Success", []
            return f"API Error: {msg} ({res})", []
            
        transfers = data.get('result', [])
        massive_transfers = []
        
        for tx in transfers:
            decimals = int(tx.get('tokenDecimal', 18))
            token_amount = float(tx['value']) / (10 ** decimals)
            usd_value = token_amount * current_price
            
            if usd_value >= 30000: # Ambang batas micin: $30k ke atas
                from_addr = tx['from'].lower()
                to_addr = tx['to'].lower()
                flow_type = "TRANSFER"
                
                if to_addr in EXCHANGE_WALLETS:
                    flow_type = "INFLOW (Potensi Jual/DUMP) 📥"
                elif from_addr in EXCHANGE_WALLETS:
                    flow_type = "OUTFLOW (Potensi Akumulasi/PUMP) 📤"
                
                massive_transfers.append({
                    'hash': tx['hash'],
                    'amount': token_amount,
                    'usd_value': usd_value,
                    'flow': flow_type
                })
        
        return "Success", massive_transfers
    except:
        return "Error", []

def verify_onchain_spike(symbol, current_price):
    """Mengecek transaksi paus di Ethereum dan BSC"""
    contract_address = STATIC_ERC20_MAPPING.get(symbol) or DYNAMIC_MAPPING.get(symbol)
    
    if not contract_address:
        return "NotSupported", []

    # 1. Coba Ethereum (Chain ID: 1)
    status, txs = get_onchain_data(ETHERSCAN_API_KEY, contract_address, current_price, 1)
    if status == "Success" and txs:
        return "Success (ETH)", txs
        
    # 2. Coba BSC (Chain ID: 56)
    bsc_api_key = os.getenv("BSCSCAN_API_KEY", "").strip('"')
    if bsc_api_key:
        status_bsc, txs_bsc = get_onchain_data(bsc_api_key, contract_address, current_price, 56)
        if status_bsc == "Success" and txs_bsc:
            return "Success (BSC)", txs_bsc

    return status, []

# --- KODE TRACKER BINANCE (SAMA SEPERTI SEBELUMNYA) ---
def get_top_futures_pairs(limit=100): # Pantau 100 koin untuk berburu micin
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        data = requests.get(url).json()
        pairs = [i for i in data if i['symbol'].endswith('USDT') and '_' not in i['symbol'] and float(i.get('quoteVolume', 0)) > 0]
        pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [i['symbol'] for i in pairs[:limit]]
    except:
        return []

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
            
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

def calculate_ema(prices, period):
    if len(prices) < period: return 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def analyze_binance(symbol):
    # Menggunakan interval 5m (5 menit) agar bot merespons seketika saat rally dimulai
    kline_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=5m&limit=24"
    depth_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=100"
    try:
        kline = requests.get(kline_url).json()
        depth = requests.get(depth_url).json()
        
        volumes = [float(c[5]) for c in kline]
        closes = [float(c[4]) for c in kline]
        price = closes[-1]
        open_price = float(kline[-1][1])
        bids = sum(float(b[0]) * float(b[1]) for b in depth.get('bids', []))
        asks = sum(float(a[0]) * float(a[1]) for a in depth.get('asks', []))
        
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 0
        spike = volumes[-1] / avg_vol if avg_vol > 0 else 0
        ob_ratio = bids / asks if asks > 0 else 0
        
        is_green = price >= open_price
        rsi = calculate_rsi(closes)
        
        # --- NEW: Trend & Market Info ---
        ema9 = calculate_ema(closes, 9)
        ema21 = calculate_ema(closes, 21)
        
        # Funding Rate & Open Interest
        funding_url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
        
        funding_data = requests.get(funding_url).json()
        oi_data = requests.get(oi_url).json()
        
        funding_rate = float(funding_data.get('lastFundingRate', 0)) * 100 
        open_interest = float(oi_data.get('openInterest', 0))
        
        # Deteksi Breakout (Menembus High 3 candle terakhir)
        highs = [float(k[2]) for k in kline[-4:-1]]
        max_high_3 = max(highs) if highs else price
        is_breakout = price > max_high_3
        
        return {
            'symbol': symbol, 'price': price, 'spike': spike, 
            'ob_ratio': ob_ratio, 'is_green': is_green, 'rsi': rsi,
            'ema9': ema9, 'ema21': ema21, 'funding': funding_rate, 
            'oi': open_interest, 'is_breakout': is_breakout
        }
    except:
        return None

def main():
    print("========================================================")
    print("   HYBRID WHALE TRACKER (CEX FUTURES + ON-CHAIN) ")
    print("========================================================")
    print("Mendeteksi Fakeout: Jika ada lonjakan di CEX, bot otomatis")
    print("mencari pembuktian paus di jaringan Ethereum (On-Chain).")
    print("========================================================\n")
    
    # Jalankan mapping koin dinamis
    load_dynamic_mapping()
    
    send_telegram_message("✅ *Hybrid Tracker (CEX + OnChain) Aktif!*\nKapan pun Anda ragu, klik tombol di bawah untuk mengecek apakah bot masih menyapu pasar.", show_button=True)
    
    empty_cycles = 0
    
    while True:
        try:
            print(f"\n[{time.strftime('%H:%M:%S')}] Memulai agregasi hibrida...")
            pairs = get_top_futures_pairs(20)
            
            whale_found = False
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(analyze_binance, pairs))
                
            for res in results:
                if not res: continue
                
                # Sinyal terdeteksi jika Spike > 3x
                is_whale_cex = False
                if res['spike'] >= 3.0:
                    is_green = res['is_green']
                    ob_ratio = res['ob_ratio']
                    
                    # Penentuan Tren berdasarkan EMA
                    trend = "SIDEWAYS"
                    if res['price'] > res['ema21'] and res['ema9'] > res['ema21']:
                        trend = "UPTREND 📈"
                    elif res['price'] < res['ema21'] and res['ema9'] < res['ema21']:
                        trend = "DOWNTREND 📉"

                    if ob_ratio >= 1.5 and is_green:
                        status = "🟢 REAL PUMP (LONG)"
                        is_whale_cex = True
                    elif ob_ratio <= 0.67 and not is_green:
                        status = "🔴 REAL DUMP (SHORT)"
                        is_whale_cex = True
                    elif res['is_breakout'] and is_green and res['spike'] >= 1.5:
                        status = "🚀 ACCUMULATION (BREAKOUT)"
                        is_whale_cex = True
                    elif ob_ratio >= 1.5 and not is_green:
                        status = "⚠️ FAKEOUT DUMP (Jangan Long!)"
                        is_whale_cex = True
                    elif ob_ratio <= 0.67 and is_green:
                        status = "⚠️ FAKEOUT PUMP (Jangan Short!)"
                        is_whale_cex = True
                        
                if is_whale_cex:
                    whale_found = True
                    print(f"\n⚡ CEX ALERT DETECTED: {res['symbol']} ({status})")
                    print("Memeriksa jaringan On-Chain Ethereum untuk validasi...")
                    
                    onchain_status, massive_txs = verify_onchain_spike(res['symbol'], res['price'])
                    
                    rsi_val = res['rsi']
                    is_green = res['is_green']
                    
                    if rsi_val >= 70:
                        rsi_text = f"🔥 {rsi_val:.1f} (Overbought)\n🔮 *Prediksi:* Rawan terbanting turun (Reversal) segera!"
                    elif rsi_val <= 30:
                        rsi_text = f"❄️ {rsi_val:.1f} (Oversold)\n🔮 *Prediksi:* Berpotensi memantul keras ke atas (V-Shape Recovery)!"
                    elif rsi_val >= 60:
                        if not is_green:
                            rsi_text = f"⚠️ {rsi_val:.1f} (Cooling Down)\n🔮 *Prediksi:* RSI mulai menukik dari puncak. Potensi koreksi turun membesar!"
                        else:
                            rsi_text = f"📈 {rsi_val:.1f} (Bullish)\n🔮 *Prediksi:* Tren naik sangat kuat, berpotensi lanjut."
                    elif rsi_val <= 40:
                        if is_green:
                            rsi_text = f"🚀 {rsi_val:.1f} (Recovery)\n🔮 *Prediksi:* RSI mulai menanjak dari dasar. Potensi pembalikan arah (Reversal Naik)!"
                        else:
                            rsi_text = f"📉 {rsi_val:.1f} (Bearish)\n🔮 *Prediksi:* Tren turun kuat, pisaunya masih meluncur."
                    else:
                        rsi_text = f"⚖️ {rsi_val:.1f} (Netral)\n🔮 *Prediksi:* Pasar berkonsolidasi, arah belum pasti."
                    
                    # Hitung TP/SL Otomatis (Risk 1:2)
                    price = res['price']
                    if "LONG" in status or (is_green and "PUMP" in status):
                        tp = price * 1.02 # +2%
                        sl = price * 0.99 # -1%
                    else:
                        tp = price * 0.98 # -2%
                        sl = price * 1.01 # +1%

                    # --- CALCULATE CONFIDENCE SCORE (0-100) ---
                    score = 0
                    
                    # 1. Volume Score (Max 30)
                    if res['spike'] >= 10: score += 30
                    elif res['spike'] >= 5: score += 20
                    else: score += 10
                    
                    # 2. Trend Score (Max 25)
                    # Sinyal searah trend = 25. Sinyal pembalikan (Fakeout) saat trend jenuh = 25.
                    if (trend == "UPTREND 📈" and ("LONG" in status or "ACCUMULATION" in status)): score += 25
                    elif (trend == "DOWNTREND 📉" and "SHORT" in status): score += 25
                    elif (trend == "UPTREND 📈" and "FAKEOUT PUMP" in status and rsi_val >= 70): score += 25
                    elif (trend == "DOWNTREND 📉" and "FAKEOUT DUMP" in status and rsi_val <= 30): score += 25
                    
                    # 3. RSI Score (Max 20)
                    if ("LONG" in status or "ACCUMULATION" in status) and rsi_val < 65: score += 20
                    elif "SHORT" in status and rsi_val > 35: score += 20
                    elif "FAKEOUT PUMP" in status and rsi_val >= 70: score += 20
                    elif "FAKEOUT DUMP" in status and rsi_val <= 30: score += 20
                    
                    # 4. On-Chain Score (Max 25)
                    if onchain_status == "Success" and massive_txs:
                        score += 25
                    
                    # Rating Penilaian
                    if score >= 80: rating = "⭐⭐⭐⭐⭐ (HIGH CONVICTION)"
                    elif score >= 60: rating = "⭐⭐⭐ (MEDIUM)"
                    else: rating = "⭐ (LOW - Hati-hati)"

                    msg = f"🚨 *HYBRID WHALE ALERT* 🚨\n\n"
                    msg += f"🔥 *{res['symbol']}* {status}\n"
                    msg += f"🏆 **Confidence Score: {score}/100**\n"
                    msg += f"📊 Rating: *{rating}*\n\n"
                    
                    msg += f"📊 Tren: *{trend}*\n"
                    msg += f"💲 Harga: ${price}\n"
                    msg += f"📊 Volume Spike: {res['spike']:.2f}x\n"
                    msg += f"🧭 RSI (5m): {rsi_text}\n"
                    msg += f"🏦 Open Interest: ${res['oi']:,.0f}\n"
                    msg += f"💳 Funding Rate: {res['funding']:.4f}%\n\n"
                    
                    msg += f"🎯 *Target Profit (2%):* ${tp:.4f}\n"
                    msg += f"🛡 *Stop Loss (1%):* ${sl:.4f}\n\n"
                    
                    if onchain_status == "Success (ETH)" or onchain_status == "Success (BSC)":
                        if massive_txs:
                            network_name = "ETHEREUM" if "ETH" in onchain_status else "BNB CHAIN"
                            msg += f"💎 *ON-CHAIN TERKONFIRMASI ({network_name})* 💎\n"
                            msg += f"Terdeteksi {len(massive_txs)} transfer > $30.000 saat ini!\n"
                            largest = max(massive_txs, key=lambda x: x['usd_value'])
                            explorer_url = f"https://etherscan.io/tx/{largest['hash']}" if "ETH" in onchain_status else f"https://bscscan.com/tx/{largest['hash']}"
                            msg += f"🐋 Aliran: *{largest['flow']}*\n"
                            msg += f"💰 Nilai: *${largest['usd_value']:,.0f}*\n"
                            msg += f"🔍 [Cek Explorer]({explorer_url})\n"
                        else:
                            msg += "❌ *ON-CHAIN FAKEOUT* ❌\n"
                            msg += "Tidak ada pergerakan Whale di Blockchain. Kemungkinan ini adalah **SPOOFING (Tembok Palsu)**!\n"
                    elif onchain_status == "NotSupported":
                        msg += "⚪ *INFO ON-CHAIN*\n"
                        msg += "Koin ini adalah koin Native atau Jaringan belum didukung untuk verifikasi On-Chain.\n"
                    else:
                        print(f"-> (Info On-Chain diabaikan karena status: {onchain_status})")
                    
                    send_telegram_message(msg)
                    time.sleep(1) # Hindari spam telegram
            
            if not whale_found:
                empty_cycles += 1
                if empty_cycles >= 10: # 10 siklus x 30 detik = 300 detik
                    send_telegram_message("✅ *Status Update*: Bot Hybrid memantau dengan stabil. Tidak ada pergerakan ekstrem dari Whale dalam 5 menit terakhir.")
                    empty_cycles = 0
            else:
                empty_cycles = 0
                
            print("Siklus selesai. Menunggu 30 second...")
            sleep_and_listen(30)
            
        except KeyboardInterrupt:
            print("\nProgram dihentikan secara manual.")
            send_telegram_message("🛑 *Bot Hybrid Dimatikan (Manual)*\nPemantauan pasar telah dihentikan.")
            break
        except Exception as e:
            error_msg = f"⚠️ *BOT ERROR*\nTerjadi kesalahan sistem:\n`{e}`\n\nMencoba restart mandiri dalam 10 detik..."
            print(f"\n[ERROR] {e}")
            send_telegram_message(error_msg)
            time.sleep(10)

if __name__ == "__main__":
    try:
        main()
    except Exception as fatal_e:
        print(f"FATAL CRASH: {fatal_e}")
        send_telegram_message(f"💀 *FATAL CRASH*\nSkrip bot mati total dan keluar dari sistem! Error:\n`{fatal_e}`")
