import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
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

DYNAMIC_MAPPING = {}

def load_dynamic_mapping():
    print("Mencoba menarik data Contract Address dari seluruh koin via CoinGecko...")
    try:
        data = requests.get("https://api.coingecko.com/api/v3/coins/list?include_platform=true").json()
        for coin in data:
            platforms = coin.get('platforms', {})
            if 'ethereum' in platforms and platforms['ethereum']:
                sym = coin['symbol'].upper() + "USDT"
                if sym not in DYNAMIC_MAPPING:
                    DYNAMIC_MAPPING[sym] = platforms['ethereum']
        print(f"Berhasil! {len(DYNAMIC_MAPPING)} koin ERC-20 kini telah terpetakan secara otomatis.\n")
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

def verify_onchain_spike(symbol, current_price):
    """Mengecek apakah ada transaksi raksasa di Blockchain pada waktu bersamaan"""
    contract_address = STATIC_ERC20_MAPPING.get(symbol) or DYNAMIC_MAPPING.get(symbol)
    
    if not contract_address:
        return "NotSupported", []
        
    api_param = f"&apikey={ETHERSCAN_API_KEY}" if ETHERSCAN_API_KEY else ""
    
    # Ambil 20 transaksi TERBARU secara global untuk koin tersebut di Ethereum
    url = f"https://api.etherscan.io/api?module=account&action=tokentx&contractaddress={contract_address}&page=1&offset=20&sort=desc{api_param}"
    
    try:
        response = requests.get(url)
        data = response.json()
        if data['status'] != '1':
            return "Error", []
            
        transfers = data['result']
        massive_transfers = []
        
        # Cari transaksi bernilai raksasa (> $100.000 USD)
        for tx in transfers:
            # Etherscan memberikan info desimal koin secara langsung pada response
            decimals = int(tx['tokenDecimal'])
            token_amount = float(tx['value']) / (10 ** decimals)
            usd_value = token_amount * current_price
            
            if usd_value >= 100000: # Batas paus: $100k ke atas
                massive_transfers.append({
                    'hash': tx['hash'],
                    'amount': token_amount,
                    'usd_value': usd_value
                })
        
        return "Success", massive_transfers
    except:
        return "Error", []

# --- KODE TRACKER BINANCE (SAMA SEPERTI SEBELUMNYA) ---
def get_top_futures_pairs(limit=20): # Batasi ke 20 agar lebih cepat
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        data = requests.get(url).json()
        pairs = [i for i in data if i['symbol'].endswith('USDT') and '_' not in i['symbol'] and float(i.get('quoteVolume', 0)) > 0]
        pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [i['symbol'] for i in pairs[:limit]]
    except:
        return []

def analyze_binance(symbol):
    # Menggunakan interval 5m (5 menit) agar bot merespons seketika saat rally dimulai
    kline_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=5m&limit=24"
    depth_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=100"
    try:
        kline = requests.get(kline_url).json()
        depth = requests.get(depth_url).json()
        
        volumes = [float(c[5]) for c in kline]
        price = float(kline[-1][4])
        open_price = float(kline[-1][1])
        bids = sum(float(b[0]) * float(b[1]) for b in depth.get('bids', []))
        asks = sum(float(a[0]) * float(a[1]) for a in depth.get('asks', []))
        
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 0
        spike = volumes[-1] / avg_vol if avg_vol > 0 else 0
        ob_ratio = bids / asks if asks > 0 else 0
        
        is_green = price >= open_price
        
        return {'symbol': symbol, 'price': price, 'spike': spike, 'ob_ratio': ob_ratio, 'is_green': is_green}
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
                    
                    if ob_ratio >= 1.5 and is_green:
                        status = "🟢 REAL PUMP (LONG)"
                        is_whale_cex = True
                    elif ob_ratio <= 0.67 and not is_green:
                        status = "🔴 REAL DUMP (SHORT)"
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
                    
                    msg = f"🚨 *HYBRID WHALE ALERT* 🚨\n\n"
                    msg += f"🔥 *{res['symbol']}* {status}\n"
                    msg += f"💲 Harga: ${res['price']}\n"
                    msg += f"📊 Volume Spike: {res['spike']:.2f}x\n\n"
                    
                    if onchain_status == "Success":
                        if massive_txs:
                            msg += "💎 *ON-CHAIN TERKONFIRMASI!* 💎\n"
                            msg += f"Terdeteksi {len(massive_txs)} transfer > $100.000 di jaringan Ethereum saat ini!\n"
                            largest = max(massive_txs, key=lambda x: x['usd_value'])
                            msg += f"🐋 Transfer Terbesar: *${largest['usd_value']:,.0f}*\n"
                            msg += f"🔍 [Cek Etherscan](https://etherscan.io/tx/{largest['hash']})\n"
                            
                            print(f"-> VALID! Ditemukan {len(massive_txs)} transfer paus. Terbesar: ${largest['usd_value']:,.0f}")
                        else:
                            msg += "❌ *ON-CHAIN FAKEOUT* ❌\n"
                            msg += "Tidak ada pergerakan Whale di Blockchain. Kemungkinan ini adalah **SPOOFING (Tembok Palsu)** oleh Whale di Exchange!\n"
                            print("-> FAKEOUT! Tidak ada transfer paus di On-Chain.")
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
            print("\nProgram dihentikan.")
            break
        except Exception as e:
            time.sleep(10)

if __name__ == "__main__":
    main()
