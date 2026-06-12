"""
TradeAI v4 AGGRESSIVE - 3 SYMBOLS (AAPL, MSFT, GOOGL)
Trade ogni 30 secondi con RSI < 40 + MACD > 0 (2 SEGNALI - NO SMA)
Railway Version - 24/7 Online - CON PAUSE BUTTON
"""

import asyncio
import json
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import os
from collections import deque

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
BASE_URL = "https://paper-api.alpaca.markets/v2"

def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return 50.0
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [c for c in changes if c > 0]
    losses = [abs(c) for c in changes if c < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26):
    if len(prices) < slow:
        return 0.0, 0.0
    ema_fast = prices[-1]
    for i in range(1, min(len(prices), fast)):
        ema_fast = ema_fast * (2/(fast+1)) + prices[-(i+1)] * (1 - 2/(fast+1))
    ema_slow = prices[-1]
    for i in range(1, min(len(prices), slow)):
        ema_slow = ema_slow * (2/(slow+1)) + prices[-(i+1)] * (1 - 2/(slow+1))
    return ema_fast - ema_slow, ema_fast

def calculate_sma(prices, period=20):
    if len(prices) < period:
        return prices[-1]
    return sum(prices[-period:]) / period

class TradePosition:
    def __init__(self, symbol, qty, side, entry_price, entry_time):
        self.symbol = symbol
        self.qty = qty
        self.side = side
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.stop_loss = entry_price * 0.99 if side == 'buy' else entry_price * 1.01
        self.take_profit = entry_price * 1.01 if side == 'buy' else entry_price * 0.99
        self.current_price = entry_price
        self.closed = False
        self.close_reason = None
        self.pnl = 0.0
    
    def update_price(self, current_price):
        self.current_price = current_price
        if self.side == 'buy':
            self.pnl = (current_price - self.entry_price) * self.qty
            if current_price <= self.stop_loss:
                self.closed = True
                self.close_reason = "STOP LOSS (-1%)"
                return 'stop_loss'
            if current_price >= self.take_profit:
                self.closed = True
                self.close_reason = "TAKE PROFIT (+1%)"
                return 'take_profit'
        return None

class IntelligentTradingBot:
    def __init__(self):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.base_url = BASE_URL
        self.running = True
        self.paused = False
        self.cycle = 0
        self.trades_placed = []
        self.initial_capital = 100000.0
        self.current_balance = 100000.0
        self.peak_balance = 100000.0
        self.startup_time = datetime.now()
        self.price_history = {
            'AAPL': deque(maxlen=100),
            'MSFT': deque(maxlen=100),
            'GOOGL': deque(maxlen=100)
        }
        self.open_positions = []
        self.drawdown_threshold = -10.0
        self.hold_time_minutes = 60
        self.stop_loss_absolute = 40.0
        self.take_profit_target = 500000.0
        self.drawdown_start_time = None
        self.under_drawdown = False
        self.max_drawdown_recorded = 0.0
    
    def get_headers(self):
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }
    
    def get_account(self):
        try:
            url = "{}/account".format(self.base_url)
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                self.account = response.json()
                self.current_balance = float(self.account.get('equity', self.current_balance))
                if self.current_balance > self.peak_balance:
                    self.peak_balance = self.current_balance
                return self.account
        except:
            pass
        return None
    
    def get_last_price(self, symbol):
        try:
            url = "{}/last_quote?symbols={}".format(self.base_url, symbol)
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'quotes' in data and symbol in data['quotes']:
                    quote = data['quotes'][symbol]
                    return (quote['ap'] + quote['bp']) / 2
        except:
            pass
        return None
    
    def place_order(self, symbol, qty, side):
        try:
            url = "{}/orders".format(self.base_url)
            data = {"symbol": symbol, "qty": qty, "side": side, "type": "market", "time_in_force": "day"}
            response = requests.post(url, headers=self.get_headers(), json=data, timeout=10)
            if response.status_code in [200, 201]:
                order = response.json()
                entry_price = order.get('filled_avg_price', 0)
                position = TradePosition(symbol, qty, side, entry_price, datetime.now())
                self.open_positions.append(position)
                self.trades_placed.append({'symbol': symbol, 'qty': qty, 'side': side, 'price': entry_price, 'time': datetime.now().strftime('%H:%M:%S'), 'reason': 'Entry'})
                return entry_price
        except:
            pass
        return None
    
    def close_position(self, position):
        try:
            url = "{}/orders".format(self.base_url)
            close_side = 'sell' if position.side == 'buy' else 'buy'
            data = {"symbol": position.symbol, "qty": position.qty, "side": close_side, "type": "market", "time_in_force": "day"}
            response = requests.post(url, headers=self.get_headers(), json=data, timeout=10)
            if response.status_code in [200, 201]:
                order = response.json()
                close_price = order.get('filled_avg_price', position.current_price)
                position.close_price = close_price
                position.closed = True
                self.trades_placed.append({'symbol': position.symbol, 'qty': position.qty, 'side': close_side, 'price': close_price, 'time': datetime.now().strftime('%H:%M:%S'), 'reason': position.close_reason, 'pnl': position.pnl})
                return True
        except:
            pass
        return False
    
    def update_positions(self):
        for symbol in ['AAPL', 'MSFT', 'GOOGL']:
            price = self.get_last_price(symbol)
            if price:
                self.price_history[symbol].append(price)
        closed_count = 0
        for position in self.open_positions:
            if not position.closed:
                price = self.get_last_price(position.symbol)
                if price:
                    exit_type = position.update_price(price)
                    if exit_type:
                        self.close_position(position)
                        closed_count += 1
        return closed_count
    
    def calculate_indicators(self, symbol):
        if len(self.price_history[symbol]) < 20:
            return None, None, None
        prices = list(self.price_history[symbol])
        rsi = calculate_rsi(prices)
        macd, _ = calculate_macd(prices)
        sma = calculate_sma(prices)
        return rsi, macd, sma
    
    def should_buy(self, symbol):
        rsi, macd, sma = self.calculate_indicators(symbol)
        if rsi is None:
            return False
        # MODIFICATO: 2 SEGNALI (RSI + MACD, ignora SMA)
        return rsi < 40 and macd > 0
    
    def calculate_drawdown(self):
        if self.peak_balance == 0:
            return 0.0
        return ((self.current_balance - self.peak_balance) / self.peak_balance) * 100
    
    def calculate_pnl_dollars(self):
        return self.current_balance - self.initial_capital
    
    def get_uptime(self):
        elapsed = datetime.now() - self.startup_time
        return "{}d {}h {}m".format(elapsed.days, elapsed.seconds // 3600, (elapsed.seconds % 3600) // 60)

bot = IntelligentTradingBot()

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>TradeAI v4 AGGRESSIVE - 2 SIGNALS</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Courier New', monospace; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: #00ff88; padding: 20px; }
.container { max-width: 1400px; margin: 0 auto; }
h1 { text-align: center; margin-bottom: 20px; font-size: 2.5em; text-shadow: 0 0 10px #00ff88; }
.status { text-align: center; padding: 15px; background: rgba(0,255,136,0.1); border: 2px solid #00ff88; border-radius: 8px; margin-bottom: 20px; font-weight: bold; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
.card { background: rgba(0,255,136,0.1); border: 2px solid #00ff88; border-radius: 8px; padding: 20px; text-align: center; }
.card-label { font-size: 0.8em; opacity: 0.7; text-transform: uppercase; margin-bottom: 10px; }
.card-value { font-size: 2em; font-weight: bold; }
.positive { color: #00ff88; }
.negative { color: #ff6b6b; }
.trades-box { background: rgba(0,255,136,0.05); border: 2px solid #00ff88; border-radius: 8px; padding: 20px; margin-top: 30px; }
.trade { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 10px; padding: 10px; border-bottom: 1px solid rgba(0,255,136,0.2); font-size: 0.85em; }
.tag { background: rgba(255,0,0,0.2); border: 2px solid #ff6b6b; padding: 8px 12px; border-radius: 4px; display: inline-block; color: #ff6b6b; font-weight: bold; margin: 0 10px 20px 0; }
.pause-btn { padding: 12px 30px; font-size: 1.1em; background: #00ff88; color: #000; border: 2px solid #00ff88; border-radius: 5px; cursor: pointer; font-weight: bold; text-transform: uppercase; transition: all 0.3s; }
.pause-btn:hover { opacity: 0.8; }
.pause-btn.paused { background: #ff6b6b; border-color: #ff6b6b; }
</style>
</head>
<body>
<div class="container">
    <h1>ROBOT TradeAI v4 AGGRESSIVE 2.0</h1>
    <div style="margin-bottom: 20px;">
        <span class="tag">AAPL + MSFT + GOOGL</span>
        <span class="tag">Trade ogni 30 sec</span>
        <span class="tag">RSI < 40 + MACD > 0</span>
    </div>
    <div style="text-align: center; margin-bottom: 20px;">
        <button id="pauseBtn" class="pause-btn">PAUSE</button>
    </div>
    <div class="status" id="status">LIVE TRADING - AGGRESSIVE STRATEGY (2 SIGNALS)</div>
    <div class="grid">
        <div class="card">
            <div class="card-label">Balance</div>
            <div class="card-value" id="balance">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">P&L</div>
            <div class="card-value" id="pnl">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Open Positions</div>
            <div class="card-value" id="open_count">0</div>
        </div>
        <div class="card">
            <div class="card-label">Total Orders</div>
            <div class="card-value" id="orders">0</div>
        </div>
        <div class="card">
            <div class="card-label">Cycles</div>
            <div class="card-value" id="cycle">0</div>
        </div>
        <div class="card">
            <div class="card-label">Uptime</div>
            <div class="card-value positive" id="uptime">0d 0h 0m</div>
        </div>
    </div>
    <div class="trades-box">
        <h2>Recent Trades (Last 15)</h2>
        <div class="trade" style="font-weight: bold; border-bottom: 2px solid #00ff88;">
            <div>SYMBOL</div><div>SIDE</div><div>PRICE</div><div>REASON</div><div>TIME</div>
        </div>
        <div id="trades-list"></div>
    </div>
</div>
<script>
document.getElementById('pauseBtn').addEventListener('click', async function() {
    let isPaused = this.textContent === 'RESUME';
    let endpoint = isPaused ? '/api/resume' : '/api/pause';
    await fetch(endpoint);
    this.textContent = isPaused ? 'PAUSE' : 'RESUME';
    this.classList.toggle('paused');
    document.getElementById('status').textContent = isPaused ? 'LIVE TRADING - AGGRESSIVE STRATEGY (2 SIGNALS)' : 'PAUSED - NO NEW TRADES';
});

async function update() {
    let res = await fetch('/api/status').then(r => r.json());
    document.getElementById('balance').textContent = '$' + res.balance.toFixed(2);
    document.getElementById('pnl').textContent = '$' + res.pnl_dollars.toFixed(2);
    document.getElementById('open_count').textContent = res.open_count;
    document.getElementById('orders').textContent = res.orders_count;
    document.getElementById('cycle').textContent = res.cycle;
    document.getElementById('uptime').textContent = res.uptime;
    let trades = await fetch('/api/trades').then(r => r.json());
    let html = trades.reverse().slice(0, 15).map(t => '<div class="trade"><div>' + t.symbol + '</div><div>' + t.side + '</div><div>$' + t.price.toFixed(2) + '</div><div>' + (t.reason || 'Trade') + '</div><div>' + t.time + '</div></div>').join('');
    document.getElementById('trades-list').innerHTML = html || '<div style="text-align:center;opacity:0.5;padding:20px;">No orders yet</div>';
}
update();
setInterval(update, 1000);
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            drawdown = bot.calculate_drawdown()
            pnl_dollars = bot.calculate_pnl_dollars()
            open_pnl = sum(p.pnl for p in bot.open_positions if not p.closed)
            open_count = len([p for p in bot.open_positions if not p.closed])
            data = {
                'balance': round(bot.current_balance, 2),
                'pnl_dollars': round(pnl_dollars, 2),
                'open_pnl': round(open_pnl, 2),
                'open_count': open_count,
                'orders_count': len(bot.trades_placed),
                'cycle': bot.cycle,
                'uptime': bot.get_uptime(),
                'paused': bot.paused
            }
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/api/trades':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(bot.trades_placed).encode())
        elif self.path == '/api/pause':
            bot.paused = True
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'paused'}).encode())
        elif self.path == '/api/resume':
            bot.paused = False
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'resumed'}).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass

async def trading_loop():
    print("\n" + "="*70)
    print("BOT v4 AGGRESSIVE 2.0 - 3 SYMBOLS (AAPL, MSFT, GOOGL)")
    print("="*70)
    print("\nStrategy: RSI < 40 + MACD > 0 (2 SIGNALS - NO SMA)")
    print("Trade every 30 seconds")
    print("Stop Loss: -1% | Take Profit: +1%\n")
    
    while bot.running:
        if bot.paused:
            await asyncio.sleep(1)
            continue
        
        bot.cycle += 1
        bot.get_account()
        closed = bot.update_positions()
        if closed > 0:
            print("Cycle {}: Closed {} positions".format(bot.cycle, closed))
        
        for symbol in ['AAPL', 'MSFT', 'GOOGL']:
            has_open = any(p.symbol == symbol and not p.closed for p in bot.open_positions)
            if not has_open and bot.should_buy(symbol):
                try:
                    entry_price = bot.place_order(symbol, 1, 'buy')
                    if entry_price:
                        rsi, macd, sma = bot.calculate_indicators(symbol)
                        print("Cycle {}: BUY {} @ ${:.2f} (RSI: {:.1f}, MACD: {:.3f})".format(bot.cycle, symbol, entry_price, rsi, macd))
                except:
                    pass
        
        if bot.cycle % 4 == 0:
            pnl = bot.calculate_pnl_dollars()
            open_count = len([p for p in bot.open_positions if not p.closed])
            print("Cycle {} | Balance: ${:.2f} | P&L: ${:.2f} | Open: {} | Orders: {}".format(bot.cycle, bot.current_balance, pnl, open_count, len(bot.trades_placed)))
        
        await asyncio.sleep(30)

def run_server():
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    print('\n' + '='*70)
    print('BOT v4 AGGRESSIVE 2.0 ONLINE ON RAILWAY - 2 SIGNALS (RSI + MACD)')
    print('='*70 + '\n')
    server.serve_forever()

if __name__ == '__main__':
    Thread(target=run_server, daemon=True).start()
    asyncio.run(trading_loop())
