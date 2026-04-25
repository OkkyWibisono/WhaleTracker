import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load konfigurasi dari file .env
load_dotenv()

# --- KONFIGURASI TELEGRAM ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram_message(text):
    """Mengirim pesan ke Telegram menggunakan Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"\n[Error] Gagal mengirim pesan Telegram: {e}")

def get_top_futures_pairs(limit=50):
    """Mengambil Top N pasangan USDT Futures dari Binance."""
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        response = requests.get(url)
        data = response.json()
        
        # Filter hanya pair USDT dan abaikan kontrak index (yg memiliki underscore '_')
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT') and '_' not in item['symbol'] and float(item.get('quoteVolume', 0)) > 0]
        
        usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [item['symbol'] for item in usdt_pairs[:limit]]
    except Exception as e:
        print(f"Error mengambil data top pair: {e}")
        return []

def analyze_exchange(symbol, exchange):
    """Menganalisa Klines dan Depth pada platform tertentu."""
    try:
        if exchange == "Binance":
            kline_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=24"
            depth_url = f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=100"
            
            kline_res = requests.get(kline_url).json()
            if len(kline_res) < 24: return None
            
            volumes = [float(c[5]) for c in kline_res]
            current_price = float(kline_res[-1][4])
            
            depth_res = requests.get(depth_url).json()
            bids = sum(float(b[0]) * float(b[1]) for b in depth_res.get('bids', []))
            asks = sum(float(a[0]) * float(a[1]) for a in depth_res.get('asks', []))
            
        elif exchange == "Bybit":
            kline_url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=60&limit=24"
            depth_url = f"https://api.bybit.com/v5/market/orderbook?category=linear&symbol={symbol}&limit=50"
            
            kline_data = requests.get(kline_url).json().get('result', {}).get('list', [])
            if len(kline_data) < 24: return None
            
            kline_data.reverse() # Bybit returns data descending
            volumes = [float(c[5]) for c in kline_data]
            current_price = float(kline_data[-1][4])
            
            depth_res = requests.get(depth_url).json().get('result', {})
            bids = sum(float(b[0]) * float(b[1]) for b in depth_res.get('b', []))
            asks = sum(float(a[0]) * float(a[1]) for a in depth_res.get('a', []))
            
        elif exchange == "OKX":
            # Convert BTCUSDT to BTC-USDT-SWAP
            okx_sym = f"{symbol[:-4]}-USDT-SWAP"
            kline_url = f"https://www.okx.com/api/v5/market/candles?instId={okx_sym}&bar=1H&limit=24"
            depth_url = f"https://www.okx.com/api/v5/market/books?instId={okx_sym}&sz=100"
            
            kline_res = requests.get(kline_url).json().get('data', [])
            if len(kline_res) < 24: return None
            
            kline_res.reverse() # OKX descending
            volumes = [float(c[5]) for c in kline_res]
            current_price = float(kline_res[-1][4])
            
            depth_res = requests.get(depth_url).json().get('data', [])
            if not depth_res: return None
            bids = sum(float(b[0]) * float(b[1]) for b in depth_res[0].get('bids', []))
            asks = sum(float(a[0]) * float(a[1]) for a in depth_res[0].get('asks', []))
            
        elif exchange == "MEXC":
            # Convert BTCUSDT to BTC_USDT
            mexc_sym = f"{symbol[:-4]}_USDT"
            kline_url = f"https://contract.mexc.com/api/v1/contract/kline/{mexc_sym}?interval=Min60"
            depth_url = f"https://contract.mexc.com/api/v1/contract/depth/{mexc_sym}?limit=100"
            
            kline_res = requests.get(kline_url).json()
            if not kline_res.get('success'): return None
            
            data = kline_res.get('data', {})
            volumes_list = data.get('vol', [])
            if len(volumes_list) < 24: return None
            
            volumes = [float(v) for v in volumes_list[-24:]]
            current_price = float(data.get('close', [])[-1])
            
            depth_res = requests.get(depth_url).json()
            if not depth_res.get('success'): return None
            
            dd = depth_res.get('data', {})
            bids = sum(float(b[0]) * float(b[1]) for b in dd.get('bids', []))
            asks = sum(float(a[0]) * float(a[1]) for a in dd.get('asks', []))
        else:
            return None

        prev_vols = volumes[:-1]
        avg_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 0
        curr_vol = volumes[-1]
        
        spike_ratio = curr_vol / avg_vol if avg_vol > 0 else 0
        ob_ratio = bids / asks if asks > 0 else 0
        
        return {
            'exchange': exchange,
            'current_price': current_price,
            'spike_ratio': spike_ratio,
            'ob_ratio': ob_ratio
        }
    except Exception:
        return None

def analyze_symbol_across_platforms(symbol, spike_threshold=3.0):
    exchanges = ["Binance", "Bybit", "OKX", "MEXC"]
    results = []
    
    # Multithreading untuk mengambil data dari 4 bursa secara bersamaan
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(analyze_exchange, symbol, ex) for ex in exchanges]
        for future in futures:
            res = future.result()
            if res:
                results.append(res)
            
    if not results:
        return None
    
    # Hitung rata-rata gabungan
    avg_spike = sum(r['spike_ratio'] for r in results) / len(results)
    avg_ob_ratio = sum(r['ob_ratio'] for r in results) / len(results)
    
    status = "Netral"
    if avg_ob_ratio >= 1.5:
        status = "Kuat Beli (Buy Wall)"
    elif avg_ob_ratio <= 0.67:
        status = "Kuat Jual (Sell Wall)"
        
    # Validasi: Rata-rata lonjakan gabungan harus > threshold dan status gabungan OB Kuat
    if avg_spike >= spike_threshold and "Kuat" in status:
        return {
            'symbol': symbol,
            'avg_spike': avg_spike,
            'agg_ob_ratio': avg_ob_ratio,
            'status': status,
            'current_price': results[0]['current_price'], 
            'details': results
        }
    return None

def main():
    print("========================================================")
    print("  MULTI-EXCHANGE WHALE TRACKER (MARKET FUTURES) ")
    print("========================================================")
    print("Platform: Binance, Bybit, OKX, MEXC (Agregasi Data)")
    print("Otomatis memindai Top 50 USDT Futures setiap 1 menit.\n")
    print("Tekan CTRL+C untuk menghentikan program.\n")
    
    send_telegram_message("✅ *Bot Futures Whale Tracker Aktif*\nPlatform: Binance + Bybit + OKX + MEXC\nMemantau Futures Top 50 tiap 1 menit...")
    
    while True:
        try:
            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Memulai siklus pemindaian baru...")
            
            pairs = get_top_futures_pairs(limit=50)
            if not pairs:
                print("Gagal mengambil data koin. Menunggu siklus berikutnya...")
                time.sleep(60)
                continue

            print(f"Ditemukan Top {len(pairs)} pasangan Futures USDT. Memulai agregasi...")
            potential_markets = []
            
            for i, symbol in enumerate(pairs): 
                print(f"[{i+1}/{len(pairs)}] Menganalisa {symbol} di 4 bursa...", end='\r')
                
                # Syarat minimal 3x lonjakan volume dari rata-rata gabungan
                result = analyze_symbol_across_platforms(symbol, spike_threshold=3.0) 
                if result:
                    potential_markets.append(result)
                    
                time.sleep(0.5) # Rate limit gabungan
                
            print("\n\n" + "="*55)
            print(" HASIL: POTENSI WHALE ENTRY (FUTURES AGGREGATION) ")
            print("="*55)
            
            if not potential_markets:
                print("Tidak ada indikasi Whale/Volume Spike yang kuat di seluruh platform.")
                send_telegram_message("ℹ️ *WHALE TRACKER UPDATE*\n\nSaat ini *TIDAK ADA* indikasi pergerakan Whale atau Volume Spike yang signifikan pada Top 50 koin Futures di keempat bursa (Binance, Bybit, OKX, MEXC).")
            else:
                potential_markets.sort(key=lambda x: x['avg_spike'], reverse=True)
                
                telegram_msg = "🚨 *CROSS-EXCHANGE WHALE ALERT* 🚨\n\n"
                
                for idx, market in enumerate(potential_markets):
                    status = market['status']
                    price = market['current_price']
                    
                    if "Beli" in status:
                        direction = "🟢 LONG (BUY)"
                        sl = price * 0.98
                        tp = price * 1.04
                    else:
                        direction = "🔴 SHORT (SELL)"
                        sl = price * 1.02
                        tp = price * 0.96
                        
                    print(f"{idx+1}. {market['symbol']} | {direction}")
                    print(f"   Harga Saat Ini:  ${price}")
                    print(f"   Rata-rata Spike: {market['avg_spike']:.2f}x (Gabungan 3 Bursa)")
                    print(f"   Rata-rata OB:    {market['agg_ob_ratio']:.2f}x -> {status}")
                    print(f"   Target Profit:   ${tp:.4f}")
                    print(f"   Stop Loss:       ${sl:.4f}")
                    print("   Rincian Per Platform:")
                    for det in market['details']:
                        print(f"      - {det['exchange']}: Spike {det['spike_ratio']:.1f}x | OB Ratio {det['ob_ratio']:.2f}x")
                    
                    telegram_msg += f"🔥 *{market['symbol']}* ({direction})\n"
                    telegram_msg += f"💲 Harga: ${price}\n"
                    telegram_msg += f"📊 Avg Spike: {market['avg_spike']:.2f}x\n"
                    telegram_msg += f"⚖️ Avg OB: {market['agg_ob_ratio']:.2f}x ({status})\n"
                    
                    platforms = " | ".join([f"{d['exchange']} {d['spike_ratio']:.1f}x" for d in market['details']])
                    telegram_msg += f"🏢 {platforms}\n"
                    
                    telegram_msg += f"🎯 TP: ${tp:.4f}\n"
                    telegram_msg += f"🛡 SL: ${sl:.4f}\n"
                    telegram_msg += "➖➖➖➖➖➖➖➖\n"
                    
                    print("-" * 30)
                    
                send_telegram_message(telegram_msg)
                    
            print("Selesai memindai. Menunggu 1 menit untuk siklus berikutnya...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            print("\n[INFO] Program dihentikan oleh user.")
            send_telegram_message("🛑 *Bot Futures Dihentikan*")
            break
        except Exception as e:
            print(f"\n[ERROR] Terjadi kesalahan: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
