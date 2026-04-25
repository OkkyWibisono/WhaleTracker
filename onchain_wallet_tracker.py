import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load konfigurasi Telegram dari file .env yang sama
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# API Key Etherscan (Bisa didapat gratis di etherscan.io, sangat disarankan agar tidak terkena rate limit)
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# =========================================================
# DAFTAR 10 TOP WHALE / SMART MONEY WALLETS (Ethereum)
# =========================================================
# Daftar ini mencakup Paus Individu, Institusi, dan Market Maker yang memindahkan volume raksasa.
WHALE_WALLETS = {
    "0x3DdfA8eC3052539b6C9549F12cEA2C295cfF5296": "Justin Sun (Whale Raksasa)",
    "0x00000000AE347930bD1E7B0F35588b92280f9e75": "Wintermute (Market Maker)",
    "0xd4B63f8E88EAF4F3B9654160a2A21b1f1A7156DE": "DWF Labs (Institusi & MM)",
    "0x18709E89BD403F470088aBDAcEbE86CC60dda12e": "Cumberland (OTC/Institusi)",
    "0x020cA66C30beC2c4Fe3861a94E4DB4A498A35872": "Machi Big Brother (Whale NFT/DeFi)",
    "0x1522900B6daFac587d499a862861C0869Be6E428": "Jump Trading (Institusi)",
    "0x05e793ce0c6027323ac150f6d45c2344d28b6019": "a16z (Venture Capital Crypto)",
    "0x71fb981f42203794ce883fb1b0bfebcf3b8d42d3": "GSR Markets (Market Maker)",
    "0x55CE1839C29F9db932baB3EBD77C85ea34B7f303": "Arthur Hayes (Eks-CEO BitMEX / Whale)",
    "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045": "Vitalik Buterin (Creator Ethereum)",
}

# Variabel untuk menyimpan transaksi masa lalu agar tidak terkirim berulang kali
last_seen_tx = {wallet: set() for wallet in WHALE_WALLETS}

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload)
    except:
        pass

def get_latest_token_transfers(wallet_address):
    """Mengambil 5 transaksi pergerakan token (ERC-20) terbaru dari wallet."""
    api_param = f"&apikey={ETHERSCAN_API_KEY}" if ETHERSCAN_API_KEY else ""
    # Menggunakan modul akun & action tokentx (Transfer Token ERC20)
    url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={wallet_address}&page=1&offset=5&sort=desc{api_param}"
    
    try:
        response = requests.get(url)
        data = response.json()
        if data['status'] == '1' and data['message'] == 'OK':
            return data['result']
        return []
    except Exception as e:
        print(f"Error mengambil data untuk {wallet_address[:6]}... : {e}")
        return []

def main():
    print("========================================================")
    print("      ON-CHAIN WHALE WALLET TRACKER (ERC-20) ")
    print("========================================================")
    print(f"Memantau {len(WHALE_WALLETS)} Wallet secara Real-time setiap 1 menit.")
    print("Sistem akan mendeteksi koin/token apa saja yang sedang mereka Beli/Jual.\n")
    
    if not ETHERSCAN_API_KEY:
        print("[WARNING] ETHERSCAN_API_KEY belum diisi di file .env!")
        print("Anda mungkin akan dibatasi jumlah requestnya. (Bisa daftar gratis di etherscan.io)\n")
        
    send_telegram_message(f"✅ *On-Chain Tracker Aktif*\nMemantau {len(WHALE_WALLETS)} wallet Whale incaran Anda...")

    # --- SINKRONISASI AWAL ---
    # Membaca riwayat transaksi terakhir agar saat program baru dijalankan, 
    # bot tidak mengirim spam semua transaksi masa lalu ke Telegram.
    print("Sinkronisasi riwayat transaksi masa lalu...")
    def sync_wallet(wallet):
        return wallet, get_latest_token_transfers(wallet)
        
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(sync_wallet, w) for w in WHALE_WALLETS.keys()]
        for future in futures:
            wallet, txs = future.result()
            for tx in txs:
                last_seen_tx[wallet].add(tx['hash'])
    print("Sinkronisasi selesai. Memulai pemantauan radar On-Chain!\n")

    # --- LOOPING PEMANTAUAN ---
    while True:
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Radar On-Chain menyapu wallet target...", end="\r")
            
            def fetch_wallet(wallet):
                return wallet, get_latest_token_transfers(wallet)
                
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_wallet, w) for w in WHALE_WALLETS.keys()]
            
            for future in futures:
                wallet, txs = future.result()
                wallet_name = WHALE_WALLETS[wallet]
                
                for tx in txs:
                    tx_hash = tx['hash']
                    
                    if tx_hash not in last_seen_tx[wallet]:
                        last_seen_tx[wallet].add(tx_hash)
                        
                        token_symbol = tx['tokenSymbol']
                        token_name = tx['tokenName']
                        
                        decimals = int(tx['tokenDecimal'])
                        value = float(tx['value']) / (10 ** decimals)
                        
                        if value == 0:
                            continue
                            
                        if tx['to'].lower() == wallet.lower():
                            action = "🟢 BUY / INCOMING"
                            emoji = "📥"
                        else:
                            action = "🔴 SELL / OUTGOING"
                            emoji = "📤"
                            
                        print(f"\n\n🚨 WHALE MOVEMENT DETECTED!")
                        print(f"Wallet: {wallet_name} ({wallet[:6]}...{wallet[-4:]})")
                        print(f"Action: {action}")
                        print(f"Koin:   {value:,.2f} {token_symbol} ({token_name})")
                        print(f"TxHash: {tx_hash}")
                        
                        msg = f"🚨 *ON-CHAIN WHALE ALERT* 🚨\n\n"
                        msg += f"👤 *Wallet:* {wallet_name}\n"
                        msg += f"`{wallet}`\n\n"
                        msg += f"{emoji} *Action:* {action}\n"
                        msg += f"💰 *Token:* {value:,.2f} *{token_symbol}*\n"
                        msg += f"📎 *Nama:* {token_name}\n\n"
                        msg += f"🔍 [Lihat Transaksi di Etherscan](https://etherscan.io/tx/{tx_hash})"
                        
                        send_telegram_message(msg)
                
            time.sleep(60) # Istirahat 1 menit sebelum radar menyapu ulang
            
        except KeyboardInterrupt:
            print("\n[INFO] Radar On-Chain dihentikan oleh user.")
            send_telegram_message("🛑 *ON-CHAIN TRACKER DIHENTIKAN*\nBot telah dimatikan secara manual oleh pengguna.")
            break
        except Exception as e:
            print(f"\n[ERROR] Terjadi exception: {e}")
            send_telegram_message(f"⚠️ *ON-CHAIN TRACKER ERROR*\nBot mengalami masalah teknis:\n`{e}`\n\nBot akan mencoba memulihkan diri dalam 10 detik.")
            time.sleep(10)

if __name__ == "__main__":
    main()
