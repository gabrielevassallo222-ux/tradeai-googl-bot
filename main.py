"""
TradeAI v4 GOOGL ONLY - INTELLIGENT TRADING BOT
Strategia RSI/MACD SOLO SU GOOGL
Focus massimo su un simbolo
"""

import asyncio
import json
import requests
import time
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
import os
from collections import deque

# ============================================================================
# ALPACA CONFIG (Via Secrets)
# ============================================================================

ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
BASE_URL = "https://paper-api.alpaca.markets/v2"

# ============================================================================
# INDICATORI TRADING
# ============================================================================

def calculate_rsi(prices, period=14):
    """Calcola RSI (Relative Strength Index)"""
    if len(prices) < period:
        return 50.0
    
    changes = []
    for i in range(1, len(prices)):
        changes.append(prices[i] - prices[i-1])
    
    gains = [c for c in changes if c > 0]
    losses = [abs(c) for c in changes if c < 0]
    
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calcola MACD (Moving Average Convergence Divergence)"""
    if len(prices) < slow:
        return 0.0, 0.0
    
    ema_fast = prices[-1]
    for i in range(1, min(len(prices), fast)):
        ema_fast = ema_fast * (2/(fast+1)) + prices[-(i+1)] * (1 - 2/(fast+1))
    
    ema_slow = prices[-1]
    for i in range(1, min(len(prices), slow)):
        ema_slow = ema_slow * (2/(slow+1)) + prices[-(i+1)] * (1 - 2/(slow+1))
    
    macd = ema_fast - ema_slow
    return macd, ema_fast

def calculate_sma(prices, period=20):
    """Calcola Media Mobile Semplice"""
    if len(prices) < period:
        return prices[-1]
    return sum(prices[-period:]) / period

# ============================================================================
# TRADE POSITION
# ============================================================================

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
        self.close_price = None
        self.pnl = 0.0
    
    def update_price(self, current_price):
        """Aggiorna prezzo corrente e controlla exit"""
        self.current_price = current_price
        
        if self.side == 'buy':
            self.pnl = (current_price - self.entry_price) * self.qty
            
            if current_price <= self.stop_loss:
                self.closed = True
                self.close_reason = f"STOP LOSS (-1%)"
                self.close_price = current_price
                return 'stop_loss'
            
            if current_price >= self.take_profit:
                self.closed = True
                self.close_reason = f"TAKE PROFIT (+1%)"
                self.close_price = current_price
                return 'take_profit'
        
        return None
    
    def get_pnl_percentage(self):
        if self.entry_price == 0:
            return 0.0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100

# ============================================================================
# INTELLIGENT TRADING BOT - GOOGL ONLY
# ============================================================================

class IntelligentTradingBot:
    def __init__(self):
        self.api_key = ALPACA_API_KEY
        self.secret_key = ALPACA_SECRET_KEY
        self.base_url = BASE_URL
        self.running = True
        self.cycle = 0
        self.trades_placed = []
        
        # Initial setup
        self.initial_capital = 100000.0
        self.current_balance = 100000.0
        self.peak_balance = 100000.0
        self.startup_time = datetime.now()
        
        # Price history SOLO GOOGL
        self.price_history = {
            'GOOGL': deque(maxlen=100)
        }
        
        # Open positions
        self.open_positions = []
        
        # Anti-Crollo
        self.drawdown_threshold = -10.0
        self.hold_time_minutes = 60
        self.stop_loss_absolute = 40.0
        self.take_profit_target = 1000.0
        self.drawdown_start_time = None
        self.under_drawdown = False
        self.max_drawdown_recorded = 0.0
        
        # Account info
        self.account = None
        self.positions = []
        self.stop_reason = None
        self.status = "TRADING"
    
    def get_headers(self):
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }
    
    def get_account(self):
        try:
            url = f"{self.base_url}/account"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                self.account = response.json()
                self.current_balance = float(self.account.get('equity', self.current_balance))
                
                if self.current_balance > self.peak_balance:
                    self.peak_balance = self.current_balance
                
                return self.account
        except Exception as e:
            print(f"Error getting account: {str(e)}")
        return None
    
    def get_last_price(self, symbol):
        """Ottiene l'ultimo prezzo da Alpaca"""
        try:
            url = f"{self.base_url}/last_quote?symbols={symbol}"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'quotes' in data and symbol in data['quotes']:
                    quote = data['quotes'][symbol]
                    price = (quote['ap'] + quote['bp']) / 2
                    return price
        except Exception as e:
            pass
        return None
    
    def get_positions(self):
        try:
            url = f"{self.base_url}/positions"
            response = requests.get(url, headers=self.get_headers(), timeout=10)
            if response.status_code == 200:
                self.positions = response.json()
                return self.positions
        except Exception as e:
            pass
        return []
    
    def place_order(self, symbol, qty, side):
        """Piazza ordine e torna il prezzo di entrata"""
        try:
            url = f"{self.base_url}/orders"
            data = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "type": "market",
                "time_in_force": "day"
            }
            response = requests.post(url, headers=self.get_headers(), json=data, timeout=10)
            if response.status_code in [200, 201]:
                order = response.json()
                entry_price = order.get('filled_avg_price', 0)
                
                position = TradePosition(symbol, qty, side, entry_price, datetime.now())
                self.open_positions.append(position)
                
                self.trades_placed.append({
                    'symbol': symbol,
                    'qty': qty,
                    'side': side,
                    'price': entry_price,
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'reason': 'Entry'
                })
                
                return entry_price
        except Exception as e:
            print(f"Error placing order: {str(e)}")
        return None
    
    def close_position(self, position):
        """Chiude una posizione aperta"""
        try:
            url = f"{self.base_url}/orders"
            close_side = 'sell' if position.side == 'buy' else 'buy'
            data = {
                "symbol": position.symbol,
                "qty": position.qty,
                "side": close_side,
                "type": "market",
                "time_in_force": "day"
            }
            response = requests.post(url, headers=self.get_headers(), json=data, timeout=10)
            if response.status_code in [200, 201]:
                order = response.json()
                close_price = order.get('filled_avg_price', position.current_price)
                position.close_price = close_price
                position.closed = True
                
                self.trades_placed.append({
                    'symbol': position.symbol,
                    'qty': position.qty,
                    'side': close_side,
                    'price': close_price,
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'reason': position.close_reason,
                    'pnl': position.pnl
                })
                
                return True
        except Exception as e:
            print(f"Error closing position: {str(e)}")
        return False
    
    def update_positions(self):
        """Aggiorna prezzi delle posizioni aperte"""
        price = self.get_last_price('GOOGL')
        if price:
            self.price_history['GOOGL'].append(price)
        
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
        """Calcola RSI, MACD, SMA per GOOGL"""
        if len(self.price_history[symbol]) < 20:
            return None, None, None
        
        prices = list(self.price_history[symbol])
        rsi = calculate_rsi(prices)
        macd, _ = calculate_macd(prices)
        sma = calculate_sma(prices)
        
        return rsi, macd, sma
    
    def should_buy(self, symbol):
        """Logica: Compra quando RSI < 40 e prezzo > SMA"""
        rsi, macd, sma = self.calculate_indicators(symbol)
        
        if rsi is None:
            return False
        
        current_price = list(self.price_history[symbol])[-1]
        
        if rsi < 40 and current_price > sma and macd > 0:
            return True
        
        return False
    
    def calculate_drawdown(self):
        if self.peak_balance == 0:
            return 0.0
        drawdown_pct = ((self.current_balance - self.peak_balance) / self.peak_balance) * 100
        return drawdown_pct
    
    def calculate_pnl_dollars(self):
        return self.current_balance - self.initial_capital
    
    def calculate_pnl_percentage(self):
        if self.initial_capital == 0:
            return 0.0
        return (self.calculate_pnl_dollars() / self.initial_capital) * 100
    
    def get_uptime(self):
        elapsed = datetime.now() - self.startup_time
        days = elapsed.days
        hours = elapsed.seconds // 3600
        minutes = (elapsed.seconds % 3600) // 60
        return f"{days}d {hours}h {minutes}m"
    
    def check_drawdown_status(self):
        drawdown = self.calculate_drawdown()
        
        if drawdown < self.max_drawdown_recorded:
            self.max_drawdown_recorded = drawdown
        
        if drawdown <= self.drawdown_threshold:
            if not self.under_drawdown:
                self.under_drawdown = True
                self.drawdown_start_time = datetime.now()
                print(f"\n⚠️  DRAWDOWN ALERT: {drawdown:.2f}% from peak")
            else:
                elapsed = datetime.now() - self.drawdown_start_time
                minutes_under = elapsed.total_seconds() / 60
                
                if minutes_under >= self.hold_time_minutes:
                    self.running = False
                    self.stop_reason = f"TRAILING STOP: {minutes_under:.0f}min under {self.drawdown_threshold}%"
                    return False
        else:
            if self.under_drawdown:
                print(f"\n✅ RECOVERED! Back above threshold")
                self.under_drawdown = False
                self.drawdown_start_time = None
        
        return True
    
    def check_exit_conditions(self):
        if not self.check_drawdown_status():
            return False
        
        if self.current_balance <= self.stop_loss_absolute:
            self.running = False
            self.stop_reason = f"ABSOLUTE STOP LOSS: ${self.current_balance:.2f}"
            return False
        
        if self.current_balance >= self.take_profit_target:
            self.running = False
            self.stop_reason = f"TAKE PROFIT TARGET REACHED: ${self.current_balance:.2f}"
            return False
        
        return True

bot = IntelligentTradingBot()

# ============================================================================
# WEB HANDLER
# ============================================================================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            drawdown = bot.calculate_drawdown()
            pnl_dollars = bot.calculate_pnl_dollars()
            pnl_percentage = bot.calculate_pnl_percentage()
            uptime = bot.get_uptime()
            pnl_color = "positive" if pnl_dollars >= 0 else "negative"
            
            time_under = 0
            if bot.under_drawdown and bot.drawdown_start_time:
                elapsed = datetime.now() - bot.drawdown_start_time
                time_under = int(elapsed.total_seconds() / 60)
            
            open_pnl = sum(p.pnl for p in bot.open_positions if not p.closed)
            open_count = len([p for p in bot.open_positions if not p.closed])
            
            html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>🤖 TradeAI v4 GOOGL ONLY</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ 
    font-family: 'Courier New', monospace;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: #00ff88;
    padding: 20px;
}}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ text-align: center; margin-bottom: 20px; font-size: 2.5em; text-shadow: 0 0 10px #00ff88; }}
.status {{ text-align: center; padding: 15px; background: rgba(0,255,136,0.1); border: 2px solid #00ff88; border-radius: 8px; margin-bottom: 20px; font-weight: bold; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
.card {{ background: rgba(0,255,136,0.1); border: 2px solid #00ff88; border-radius: 8px; padding: 20px; text-align: center; }}
.card-label {{ font-size: 0.8em; opacity: 0.7; text-transform: uppercase; margin-bottom: 10px; }}
.card-value {{ font-size: 2em; font-weight: bold; }}
.positive {{ color: #00ff88; }}
.negative {{ color: #ff6b6b; }}
.warning {{ color: #ffd700; }}
.protection-bar {{
    background: rgba(0,255,136,0.05);
    border: 2px solid #00ff88;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
}}
.protection-item {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 20px;
    margin-bottom: 15px;
}}
.protection-stat {{
    background: rgba(0,255,136,0.1);
    border: 1px solid #00ff88;
    border-radius: 5px;
    padding: 15px;
    text-align: center;
}}
.protection-label {{ font-size: 0.75em; opacity: 0.7; text-transform: uppercase; margin-bottom: 8px; }}
.protection-value {{ font-size: 1.5em; font-weight: bold; }}
.trades-box {{ background: rgba(0,255,136,0.05); border: 2px solid #00ff88; border-radius: 8px; padding: 20px; }}
.trade {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr; gap: 10px; padding: 10px; border-bottom: 1px solid rgba(0,255,136,0.2); font-size: 0.85em; }}
.alert {{ background: rgba(255,215,0,0.1); border: 2px solid #ffd700; padding: 15px; border-radius: 8px; margin-bottom: 20px; color: #ffd700; }}
.tag {{ background: rgba(0,200,255,0.2); border: 2px solid #00c8ff; padding: 8px 12px; border-radius: 4px; display: inline-block; color: #00c8ff; font-weight: bold; margin: 0 10px 20px 0; }}
</style>
</head>
<body>
<div class="container">
    <h1>🤖 TradeAI v4 GOOGL ONLY</h1>
    
    <div style="margin-bottom: 20px;">
        <span class="tag">📍 SOLO GOOGL</span>
        <span class="tag">🎯 FOCUSED</span>
        <span class="tag">RSI < 40</span>
        <span class="tag">Stop -1% / Take +1%</span>
    </div>
    
    <div class="status">
        ✅ LIVE TRADING - GOOGL FOCUSED STRATEGY
    </div>
    
    {f'<div class="alert">⚠️  DRAWDOWN DETECTED: {time_under} min under -{abs(bot.drawdown_threshold):.0f}% | Will stop if {bot.hold_time_minutes}min is reached</div>' if bot.under_drawdown else ''}
    
    <div class="protection-bar">
        <h2>🛡️ ANTI-CROLLO PROTECTION</h2>
        <div class="protection-item">
            <div class="protection-stat">
                <div class="protection-label">📉 Current Drawdown</div>
                <div class="protection-value {\'warning\' if drawdown <= bot.drawdown_threshold else \'positive\'}">{drawdown:.2f}%</div>
            </div>
            <div class="protection-stat">
                <div class="protection-label">⏱️ Time Under Limit</div>
                <div class="protection-value {\'warning\' if time_under > 30 else \'positive\'}">{time_under}/{bot.hold_time_minutes} min</div>
            </div>
            <div class="protection-stat">
                <div class="protection-label">📊 Max Drawdown</div>
                <div class="protection-value negative">{bot.max_drawdown_recorded:.2f}%</div>
            </div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <div class="card-label">💰 Balance</div>
            <div class="card-value" id="balance">${{bot.current_balance:.2f}}</div>
        </div>
        <div class="card">
            <div class="card-label">📊 P&L Totale</div>
            <div class="card-value {pnl_color}" id="pnl">${{pnl_dollars:.2f}} ({pnl_percentage:.2f}%)</div>
        </div>
        <div class="card">
            <div class="card-label">📈 Open P&L</div>
            <div class="card-value {('positive' if open_pnl >= 0 else 'negative')}" id="open_pnl">${{open_pnl:.2f}}</div>
        </div>
        <div class="card">
            <div class="card-label">📍 Open Positions</div>
            <div class="card-value" id="open_count">{open_count}</div>
        </div>
        <div class="card">
            <div class="card-label">📈 Peak</div>
            <div class="card-value positive">${{{bot.peak_balance:.2f}}}</div>
        </div>
        <div class="card">
            <div class="card-label">⏱️ Uptime</div>
            <div class="card-value positive">{uptime}</div>
        </div>
        <div class="card">
            <div class="card-label">📊 Total Orders</div>
            <div class="card-value" id="orders">{len(bot.trades_placed)}</div>
        </div>
        <div class="card">
            <div class="card-label">🔄 Cycles</div>
            <div class="card-value" id="cycle">{bot.cycle}</div>
        </div>
    </div>
    
    <div class="trades-box">
        <h2>📋 Recent Trades - GOOGL (Ultimi 15)</h2>
        <div class="trade" style="font-weight: bold; border-bottom: 2px solid #00ff88;">
            <div>SYMBOL</div>
            <div>SIDE</div>
            <div>PRICE</div>
            <div>REASON</div>
            <div>TIME</div>
        </div>
        <div id="trades-list"></div>
    </div>
</div>

<script>
async function update() {{
    let res = await fetch('/api/status').then(r => r.json());
    
    document.getElementById('balance').textContent = '$' + res.balance.toFixed(2);
    document.getElementById('pnl').textContent = '$' + res.pnl_dollars.toFixed(2) + ' (' + res.pnl_percentage.toFixed(2) + '%)';
    document.getElementById('open_pnl').textContent = '$' + res.open_pnl.toFixed(2);
    document.getElementById('open_count').textContent = res.open_count;
    document.getElementById('orders').textContent = res.orders_count;
    document.getElementById('cycle').textContent = res.cycle;
    
    if (res.pnl_dollars >= 0) {{
        document.getElementById('pnl').style.color = '#00ff88';
    }} else {{
        document.getElementById('pnl').style.color = '#ff6b6b';
    }}
    
    let trades = await fetch('/api/trades').then(r => r.json());
    let html = trades.reverse().slice(0, 15).map(t => `
        <div class="trade">
            <div>${{t.symbol}}</div>
            <div>${{t.side}}</div>
            <div>$${{t.price.toFixed(2)}}</div>
            <div>${{t.reason || 'Trade'}}</div>
            <div>${{t.time}}</div>
        </div>
    `).join('');
    document.getElementById('trades-list').innerHTML = html || '<div style="text-align:center;opacity:0.5;padding:20px;">Nessun ordine ancora</div>';
}}

update();
setInterval(update, 1000);
</script>
</body>
</html>'''
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            drawdown = bot.calculate_drawdown()
            pnl_dollars = bot.calculate_pnl_dollars()
            pnl_percentage = bot.calculate_pnl_percentage()
            open_pnl = sum(p.pnl for p in bot.open_positions if not p.closed)
            open_count = len([p for p in bot.open_positions if not p.closed])
            
            data = {
                'balance': round(bot.current_balance, 2),
                'peak': round(bot.peak_balance, 2),
                'pnl_dollars': round(pnl_dollars, 2),
                'pnl_percentage': round(pnl_percentage, 2),
                'open_pnl': round(open_pnl, 2),
                'open_count': open_count,
                'drawdown': round(drawdown, 2),
                'orders_count': len(bot.trades_placed),
                'cycle': bot.cycle,
                'running': bot.running,
                'under_drawdown': bot.under_drawdown,
                'max_drawdown': round(bot.max_drawdown_recorded, 2)
            }
            self.wfile.write(json.dumps(data).encode())
        
        elif self.path == '/api/trades':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(bot.trades_placed).encode())
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, *args):
        pass

async def trading_loop():
    print("\n" + "="*70)
    print("🤖 BOT v4 GOOGL ONLY - INTELLIGENT TRADING BOT".center(70))
    print("="*70)
    print(f"\n📍 FOCUS TOTALE SU GOOGL")
    print(f"   RSI Threshold: < 40")
    print(f"   Stop Loss: -1%")
    print(f"   Take Profit: +1%")
    print(f"   Trade ogni 30 secondi\n")
    
    while bot.running:
        bot.cycle += 1
        
        bot.get_account()
        bot.get_positions()
        
        closed = bot.update_positions()
        if closed > 0:
            print(f"Cycle {bot.cycle}: Chiuse {closed} posizioni GOOGL")
        
        if not bot.check_exit_conditions():
            print(f"\n🛑 {bot.stop_reason}")
            break
        
        # SOLO GOOGL
        symbol = 'GOOGL'
        has_open = any(p.symbol == symbol and not p.closed for p in bot.open_positions)
        
        if not has_open and bot.should_buy(symbol):
            try:
                qty = 1
                entry_price = bot.place_order(symbol, qty, 'buy')
                if entry_price:
                    rsi, macd, sma = bot.calculate_indicators(symbol)
                    print(f"Cycle {bot.cycle}: BUY GOOGL @ ${entry_price:.2f} (RSI: {rsi:.1f}, MACD: {macd:.3f})")
            except Exception as e:
                pass
        
        if bot.cycle % 4 == 0:
            drawdown = bot.calculate_drawdown()
            pnl = bot.calculate_pnl_dollars()
            open_count = len([p for p in bot.open_positions if not p.closed])
            print(f"Cycle {bot.cycle} | Balance: ${bot.current_balance:.2f} | P&L: ${pnl:.2f} | Open: {open_count} | Orders: {len(bot.trades_placed)}")
        
        await asyncio.sleep(30)

def run_server():
    server = HTTPServer(('0.0.0.0', 8000), Handler)
    print('\n' + '='*70)
    print('🚀 BOT v4 GOOGL ONLY ONLINE'.center(70))
    print('='*70)
    print('\n📱 Apri nel browser la URL Replit')
    print('📍 Focus: SOLO GOOGL')
    print('🧠 Strategia: RSI < 40 + MACD\n')
    server.serve_forever()

if __name__ == '__main__':
    Thread(target=run_server, daemon=True).start()
    asyncio.run(trading_loop())
