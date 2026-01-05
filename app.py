from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import json
import re
import base64
import requests
import traceback

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

exchange_rates_cache = {}

def get_exchange_rates():
    """Get real-time exchange rates"""
    global exchange_rates_cache
    try:
        response = requests.get('https://api.exchangerate-api.com/v4/latest/EUR', timeout=5)
        data = response.json()
        exchange_rates_cache = {
            'EUR_TO_AED': data['rates']['AED'],
            'EUR_TO_USD': data['rates']['USD'],
            'AED_TO_EUR': 1 / data['rates']['AED'],
            'USD_TO_EUR': 1 / data['rates']['USD'],
            'AED_TO_USD': data['rates']['USD'] / data['rates']['AED'],
            'USD_TO_AED': data['rates']['AED'] / data['rates']['USD'],
            'timestamp': data['time_last_updated']
        }
        return exchange_rates_cache
    except Exception as e:
        print(f"Exchange rate API error: {e}")
        return {
            'EUR_TO_AED': 3.95, 'EUR_TO_USD': 1.09,
            'AED_TO_EUR': 0.253, 'USD_TO_EUR': 0.917,
            'AED_TO_USD': 0.272, 'USD_TO_AED': 3.67,
            'timestamp': 'fallback'
        }

def detect_image_type(base64_string):
    """Detect image type from base64"""
    try:
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        img_data = base64.b64decode(base64_string[:100])
        if img_data.startswith(b'\xff\xd8\xff'): 
            return 'image/jpeg'
        elif img_data.startswith(b'\x89PNG\r\n\x1a\n'): 
            return 'image/png'
        elif img_data.startswith(b'GIF87a') or img_data.startswith(b'GIF89a'): 
            return 'image/gif'
        elif img_data[0:4] == b'RIFF' and img_data[8:12] == b'WEBP': 
            return 'image/webp'
        elif b'ftyp' in img_data[4:12]:
            if b'avif' in img_data[8:20] or b'avis' in img_data[8:20]: 
                return 'image/avif'
    except Exception as e:
        print(f"Image type detection error: {e}")
    
    if base64_string.startswith('/9j/'): 
        return 'image/jpeg'
    elif base64_string.startswith('iVBOR'): 
        return 'image/png'
    elif base64_string.startswith('R0lGO'): 
        return 'image/gif'
    elif base64_string.startswith('UklGR'): 
        return 'image/webp'
    
    return 'image/jpeg'

def calculate_bpm(co2, year, fuel_type):
    """Calculate Dutch BPM tax"""
    age = 2025 - year
    if age >= 5: return 0
    bpm = 400
    if co2 > 82:
        bpm += (min(co2,140)-82)*80
        if co2 > 140: bpm += (min(co2,180)-140)*120
        if co2 > 180: bpm += (co2-180)*180
    if fuel_type.lower()=='diesel' and co2>82: bpm += (co2-82)*90
    return round(bpm * (1 - min(age*0.2, 1.0)), 2)

def calculate_shipping_cost(container_type, vehicle_dimensions):
    """Calculate detailed shipping costs"""
    if container_type == 'roro':
        base_cost = 800
        if vehicle_dimensions.get('length', 0) > 5: base_cost += 200
        if vehicle_dimensions.get('height', 0) > 2: base_cost += 150
        return {
            'shipping_method': 'RoRo (Roll-on/Roll-off)',
            'base_shipping': base_cost, 'loading_fee': 150,
            'unloading_fee': 150, 'securing_fee': 50,
            'insurance': 100, 'total': base_cost + 450
        }
    elif container_type == 'container_20ft':
        return {
            'shipping_method': '20ft Container',
            'base_shipping': 1500, 'loading_fee': 200,
            'unloading_fee': 200, 'securing_fee': 100,
            'container_rental': 150, 'insurance': 150, 'total': 2300
        }
    elif container_type == 'container_40ft':
        return {
            'shipping_method': '40ft Container',
            'base_shipping': 2200, 'loading_fee': 300,
            'unloading_fee': 300, 'securing_fee': 150,
            'container_rental': 200, 'insurance': 250, 'total': 3400
        }
    return calculate_shipping_cost('roro', vehicle_dimensions)

def estimate_market_price_ai(vehicle_data):
    """Use Claude AI to estimate EU market price"""
    if not client:
        return None
    
    try:
        prompt = f"""You are an automotive market analyst. Estimate the current EU market price (in EUR) for this vehicle:

Make: {vehicle_data.get('marca', 'Unknown')}
Model: {vehicle_data.get('model', 'Unknown')}
Year: {vehicle_data.get('year', '2020')}
Engine: {vehicle_data.get('engine', '2.0L')}
Fuel: {vehicle_data.get('fuel_type', 'benzina')}
CO2: {vehicle_data.get('co2', '180')} g/km

Consider:
- Current market trends in Germany/Netherlands
- Typical depreciation for this make/model
- Premium for low mileage (assume 100k-150k km)
- Market demand for this vehicle type

Provide realistic price range and average. Return JSON only:
{{"min_price": 25000, "max_price": 35000, "avg_price": 30000, "confidence": "high", "notes": "Popular model, strong demand"}}"""

        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        txt = re.sub(r'^```json\s*|\s*```$', '', msg.content[0].text.strip(), flags=re.MULTILINE)
        result = json.loads(txt)
        return result
        
    except Exception as e:
        print(f"Market estimation error: {e}")
        traceback.print_exc()
        return None

@app.route('/')
def home():
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Vehicle Import Calculator v2.0</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:10px}@media(min-width:768px){body{padding:20px}}.container{max-width:1100px;margin:0 auto;background:white;border-radius:20px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}@media(min-width:768px){.container{padding:40px}}h1{color:#667eea;text-align:center;margin-bottom:10px;font-size:1.5em}@media(min-width:768px){h1{font-size:2em}}.subtitle{text-align:center;color:#666;margin-bottom:20px;font-size:0.9em}@media(min-width:768px){.subtitle{margin-bottom:30px;font-size:1em}}.version{text-align:center;color:#999;font-size:0.75em;margin-bottom:15px}@media(min-width:768px){.version{font-size:0.85em;margin-bottom:20px}}.upload-zone{border:3px dashed #667eea;border-radius:15px;padding:20px;text-align:center;cursor:pointer;transition:all 0.3s;margin-bottom:10px}@media(min-width:768px){.upload-zone{padding:40px;margin-bottom:15px}}.upload-zone:hover{background:#f8f9ff}.upload-zone.dragover{background:#e8ebff;border-color:#764ba2}.upload-zone p{font-size:0.9em}@media(min-width:768px){.upload-zone p{font-size:1em}}.manual-entry-btn{background:linear-gradient(135deg,#28a745 0%,#20c997 100%);color:white;border:none;padding:12px 20px;border-radius:10px;font-size:1em;cursor:pointer;width:100%;margin-bottom:20px;transition:all 0.3s}@media(min-width:768px){.manual-entry-btn{padding:15px 30px;font-size:1.1em;margin-bottom:30px}}.manual-entry-btn:hover{transform:translateY(-2px);box-shadow:0 5px 15px rgba(40,167,69,0.3)}.image-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:15px 0}@media(min-width:768px){.image-grid{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}}.image-preview{max-width:100%;height:120px;object-fit:cover;border-radius:10px;border:2px solid #667eea}@media(min-width:768px){.image-preview{height:150px}}.image-slot{position:relative;text-align:center;padding:8px;background:#f8f9ff;border-radius:10px}@media(min-width:768px){.image-slot{padding:10px}}.remove-image{position:absolute;top:3px;right:3px;background:red;color:white;border:none;border-radius:50%;width:20px;height:20px;cursor:pointer;font-weight:bold;font-size:0.8em}@media(min-width:768px){.remove-image{top:5px;right:5px;width:25px;height:25px;font-size:1em}}.loading{text-align:center;padding:20px;display:none}.spinner{border:4px solid #f3f3f3;border-top:4px solid #667eea;border-radius:50%;width:40px;height:40px;animation:spin 1s linear infinite;margin:0 auto 10px}@media(min-width:768px){.spinner{width:50px;height:50px}}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}.result-grid{display:grid;grid-template-columns:1fr;gap:10px;margin:15px 0}@media(min-width:768px){.result-grid{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}}.result-item{background:#f8f9ff;padding:12px;border-radius:10px}@media(min-width:768px){.result-item{padding:15px}}.result-label{font-size:0.8em;color:#666;margin-bottom:5px}@media(min-width:768px){.result-label{font-size:0.85em}}.edit-input{width:100%;padding:8px;border:2px solid #667eea;border-radius:5px;font-size:0.9em;margin-top:5px}@media(min-width:768px){.edit-input{font-size:1em}}button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:12px 20px;border-radius:10px;font-size:1em;cursor:pointer;width:100%;margin:10px 0}@media(min-width:768px){button{padding:15px 30px;font-size:1.1em}}button:hover{transform:translateY(-2px)}button:disabled{opacity:0.5;cursor:not-allowed}.price-section{background:#f8f9ff;padding:15px;border-radius:10px;margin:15px 0}@media(min-width:768px){.price-section{padding:20px;margin:20px 0}}.price-grid{display:grid;grid-template-columns:1fr;gap:10px;margin-bottom:15px}@media(min-width:768px){.price-grid{grid-template-columns:1fr 1fr 1fr;gap:15px;margin-bottom:20px}}.price-input{width:100%;padding:12px;font-size:1em;border:2px solid #667eea;border-radius:10px}@media(min-width:768px){.price-input{padding:15px;font-size:1.1em}}.shipping-section{background:#fff3cd;padding:15px;border-radius:10px;margin:15px 0}@media(min-width:768px){.shipping-section{padding:20px;margin:20px 0}}.shipping-options{display:grid;grid-template-columns:1fr;gap:10px;margin:10px 0}@media(min-width:768px){.shipping-options{grid-template-columns:repeat(3,1fr);gap:15px;margin:15px 0}}.shipping-option{padding:12px;border:2px solid #ddd;border-radius:10px;cursor:pointer;text-align:center;transition:all 0.3s}@media(min-width:768px){.shipping-option{padding:15px}}.shipping-option:hover,.shipping-option.selected{border-color:#667eea;background:#f8f9ff}.dimension-inputs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}@media(min-width:768px){.dimension-inputs{grid-template-columns:repeat(4,1fr);gap:10px;margin:15px 0}}.dimension-input{padding:8px;border:2px solid #ddd;border-radius:5px;font-size:0.9em}@media(min-width:768px){.dimension-input{padding:10px;font-size:1em}}.cost-comparison{display:grid;grid-template-columns:1fr;gap:15px;margin:15px 0}@media(min-width:768px){.cost-comparison{grid-template-columns:repeat(3,1fr);gap:20px;margin:20px 0}}.cost-card{background:white;border:2px solid #ddd;border-radius:15px;padding:15px}@media(min-width:768px){.cost-card{padding:20px}}.cost-card.recommended{border-color:#28a745;background:#f0fff4}.cost-card h3{margin-bottom:10px;color:#667eea;font-size:1em}@media(min-width:768px){.cost-card h3{margin-bottom:15px;font-size:1.2em}}.cost-line{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #eee;font-size:0.85em}@media(min-width:768px){.cost-line{padding:8px 0;font-size:1em}}.cost-total{font-size:1.1em;font-weight:bold;color:#667eea;margin-top:8px}@media(min-width:768px){.cost-total{font-size:1.3em;margin-top:10px}}.recommendation{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:15px;border-radius:15px;text-align:center;font-size:1em;margin:15px 0}@media(min-width:768px){.recommendation{padding:20px;font-size:1.2em;margin:20px 0}}.exchange-info{text-align:center;color:#666;font-size:0.75em;margin:8px 0;padding:8px;background:#fff;border-radius:5px}@media(min-width:768px){.exchange-info{font-size:0.85em;margin:10px 0;padding:10px}}.shipping-details{background:#f8f9ff;padding:12px;border-radius:10px;margin:12px 0}@media(min-width:768px){.shipping-details{padding:15px;margin:15px 0}}.shipping-breakdown{display:grid;grid-template-columns:1fr auto;gap:8px;margin:8px 0;font-size:0.8em}@media(min-width:768px){.shipping-breakdown{gap:10px;margin:10px 0;font-size:0.9em}}.alert{padding:12px;border-radius:10px;margin:15px 0;font-size:0.85em}@media(min-width:768px){.alert{padding:15px;margin:20px 0;font-size:1em}}.alert-info{background:#d1ecf1;border:1px solid #bee5eb;color:#0c5460}.profitability-section{margin:20px 0}@media(min-width:768px){.profitability-section{margin:30px 0}}.profitability-card{padding:20px;border-radius:15px;border:3px solid;margin:15px 0}@media(min-width:768px){.profitability-card{padding:25px;margin:20px 0}}.profit-high{background:#d4edda;border-color:#28a745;color:#155724}.profit-medium{background:#fff3cd;border-color:#ffc107;color:#856404}.profit-low{background:#f8d7da;border-color:#dc3545;color:#721c24}.market-estimate{background:#e7f3ff;padding:15px;border-radius:10px;margin:15px 0;border-left:5px solid #667eea}@media(min-width:768px){.market-estimate{padding:20px;margin:20px 0}}.market-sources{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}@media(min-width:768px){.market-sources{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:15px 0}}.source-badge{padding:6px;background:#f8f9ff;border-radius:5px;text-align:center;font-size:0.7em;border:1px solid #ddd}@media(min-width:768px){.source-badge{padding:8px;font-size:0.85em}}.profit-breakdown{display:grid;grid-template-columns:1fr auto;gap:10px;margin:10px 0;font-size:0.95em;padding:8px;background:#fff;border-radius:5px}@media(min-width:768px){.profit-breakdown{gap:15px;margin:15px 0;font-size:1.1em;padding:10px}}.profit-percentage{font-size:1.5em;font-weight:bold;text-align:center;margin:15px 0}@media(min-width:768px){.profit-percentage{font-size:2em;margin:20px 0}}.manual-override{background:#fff3cd;padding:12px;border-radius:10px;margin:12px 0;border-left:5px solid #ffc107}@media(min-width:768px){.manual-override{padding:15px;margin:15px 0}}h2,h3,h4{font-size:1.2em;margin-bottom:10px}@media(min-width:768px){h2,h3,h4{font-size:1.5em;margin-bottom:15px}}</style></head><body><div class="container"><h1>🚗 Vehicle Import Calculator</h1><p class="subtitle">Dubai → Rotterdam → EU | AI-Powered Analysis</p><p class="version">v2.0 Phase 2 - Mobile Optimized | Easy Reset</p><div class="upload-zone" id="uploadZone" onclick="resetAnalysis();uploadZone.click()"><p>📸 Upload up to 4 vehicle photos</p><p style="font-size:0.8em;color:#666;margin-top:8px">Click or drag & drop</p><input type="file" id="fileInput" accept="image/*" multiple style="display:none"></div><button class="manual-entry-btn" onclick="resetAnalysis();showManualEntry()">✍️ Add manual vehicle specs</button><div class="image-grid" id="imageGrid"></div><div class="loading" id="loading"><div class="spinner"></div><p>Analyzing with Claude AI...</p></div><div id="vehicleResults" style="display:none"><h2>Vehicle Analysis</h2><div class="result-grid"><div class="result-item"><div class="result-label">Make & Model</div><input type="text" id="edit_marca" class="edit-input" placeholder="Make"><input type="text" id="edit_model" class="edit-input" placeholder="Model" style="margin-top:5px"></div><div class="result-item"><div class="result-label">Year</div><input type="number" id="edit_year" class="edit-input" placeholder="2020"></div><div class="result-item"><div class="result-label">Engine</div><input type="text" id="edit_engine" class="edit-input" placeholder="2.0L"></div><div class="result-item"><div class="result-label">Fuel</div><select id="edit_fuel" class="edit-input"><option value="benzina">Benzina</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option></select></div><div class="result-item"><div class="result-label">CO2 (g/km)</div><input type="number" id="edit_co2" class="edit-input" placeholder="180"></div></div><div class="shipping-section"><h3>🚢 Shipping</h3><div class="shipping-options"><div class="shipping-option" data-method="roro" onclick="selectShipping('roro')"><strong>RoRo</strong><p style="font-size:0.75em;margin-top:3px">Cheapest</p></div><div class="shipping-option" data-method="container_20ft" onclick="selectShipping('container_20ft')"><strong>20ft</strong><p style="font-size:0.75em;margin-top:3px">Secure</p></div><div class="shipping-option" data-method="container_40ft" onclick="selectShipping('container_40ft')"><strong>40ft</strong><p style="font-size:0.75em;margin-top:3px">Large</p></div></div><h4 style="margin:10px 0 8px;font-size:1em">Dimensions (Optional)</h4><div class="dimension-inputs"><input type="number" id="dim_length" class="dimension-input" placeholder="Length (m)" step="0.1"><input type="number" id="dim_width" class="dimension-input" placeholder="Width (m)" step="0.1"><input type="number" id="dim_height" class="dimension-input" placeholder="Height (m)" step="0.1"><input type="number" id="dim_weight" class="dimension-input" placeholder="Weight (kg)"></div></div><div class="price-section"><h3>💰 Purchase Price</h3><div class="price-grid"><div><label style="font-size:0.85em;color:#666">AED</label><input type="number" id="priceAED" class="price-input" placeholder="0" oninput="convertCurrency('AED')"></div><div><label style="font-size:0.85em;color:#666">USD</label><input type="number" id="priceUSD" class="price-input" placeholder="0" oninput="convertCurrency('USD')"></div><div><label style="font-size:0.85em;color:#666">EUR</label><input type="number" id="priceEUR" class="price-input" placeholder="0" oninput="convertCurrency('EUR')"></div></div><div class="exchange-info" id="exchangeInfo">Loading...</div><button onclick="calculateCosts()">📊 Calculate Costs</button></div></div><div id="costResults" style="display:none"><h2>💶 Cost Analysis</h2><div class="alert alert-info"><strong>Three scenarios:</strong> FREE ZONE | STANDARD | 🎯 NO BPM</div><div class="cost-comparison"><div class="cost-card" id="freeZoneCard"><h3>🆓 FREE ZONE</h3><div id="freeZoneCosts"></div></div><div class="cost-card" id="standardCard"><h3>📋 STANDARD</h3><div id="standardCosts"></div></div><div class="cost-card" id="noBpmCard"><h3>🎯 NO BPM</h3><div id="noBpmCosts"></div></div></div><div class="shipping-details" id="shippingBreakdown"></div><div class="recommendation" id="recommendation"></div><div class="profitability-section" id="profitabilitySection" style="display:none"><h2>📈 Profitability</h2><div class="market-estimate" id="marketEstimate"></div><div class="manual-override"><h4 style="font-size:1em">💡 Manual Override</h4><p style="font-size:0.85em;margin:8px 0">Know the market price? Enter it:</p><input type="number" id="manualMarketPrice" class="price-input" placeholder="Market price (EUR)" oninput="recalculateProfit()"></div><div id="profitabilityCard"></div></div></div></div><script>let vehicleData={};let uploadedImages=[];let selectedShipping='roro';let exchangeRates={};let marketEstimate=null;let calculatedCosts=null;const MAX_IMAGES=4;const uploadZone=document.getElementById('uploadZone');const fileInput=document.getElementById('fileInput');const imageGrid=document.getElementById('imageGrid');function resetAnalysis(){uploadedImages=[];vehicleData={};marketEstimate=null;calculatedCosts=null;imageGrid.innerHTML='';document.getElementById('vehicleResults').style.display='none';document.getElementById('costResults').style.display='none';document.getElementById('profitabilitySection').style.display='none';document.getElementById('edit_marca').value='';document.getElementById('edit_model').value='';document.getElementById('edit_year').value='';document.getElementById('edit_engine').value='';document.getElementById('edit_fuel').value='benzina';document.getElementById('edit_co2').value='';document.getElementById('priceAED').value='';document.getElementById('priceUSD').value='';document.getElementById('priceEUR').value='';document.getElementById('manualMarketPrice').value='';fileInput.value='';window.scrollTo({top:0,behavior:'smooth'})}uploadZone.ondragover=(e)=>{e.preventDefault();uploadZone.classList.add('dragover')};uploadZone.ondragleave=()=>uploadZone.classList.remove('dragover');uploadZone.ondrop=(e)=>{e.preventDefault();uploadZone.classList.remove('dragover');handleFiles(e.dataTransfer.files)};fileInput.onchange=(e)=>handleFiles(e.target.files);function showManualEntry(){document.getElementById('vehicleResults').style.display='block';document.getElementById('edit_marca').focus();document.getElementById('edit_marca').scrollIntoView({behavior:'smooth',block:'center'});selectShipping('roro')}function handleFiles(files){if(uploadedImages.length>=MAX_IMAGES){alert('Maximum 4 images');return}Array.from(files).slice(0,MAX_IMAGES-uploadedImages.length).forEach(file=>{if(!file.type.startsWith('image/')){alert('Only images');return}const reader=new FileReader();reader.onload=(e)=>{uploadedImages.push(e.target.result);displayImages();if(uploadedImages.length===1){analyzeVehicle()}};reader.readAsDataURL(file)})}function displayImages(){imageGrid.innerHTML='';uploadedImages.forEach((img,idx)=>{const slot=document.createElement('div');slot.className='image-slot';slot.innerHTML='<img src="'+img+'" class="image-preview"><button class="remove-image" onclick="removeImage('+idx+')">×</button><p style="font-size:0.7em;margin-top:3px">Photo '+(idx+1)+'</p>';imageGrid.appendChild(slot)})}function removeImage(idx){uploadedImages.splice(idx,1);displayImages()}function selectShipping(method){selectedShipping=method;document.querySelectorAll('.shipping-option').forEach(el=>el.classList.remove('selected'));document.querySelector('[data-method="'+method+'"]').classList.add('selected')}async function loadExchangeRates(){try{const response=await fetch('/api/exchange-rates');exchangeRates=await response.json();document.getElementById('exchangeInfo').innerHTML='💱 1 EUR = '+exchangeRates.EUR_TO_AED.toFixed(2)+' AED | '+exchangeRates.EUR_TO_USD.toFixed(2)+' USD'}catch(e){console.error(e)}}loadExchangeRates();function convertCurrency(from){const aed=parseFloat(document.getElementById('priceAED').value)||0;const usd=parseFloat(document.getElementById('priceUSD').value)||0;const eur=parseFloat(document.getElementById('priceEUR').value)||0;if(from==='AED'&&aed>0){document.getElementById('priceEUR').value=Math.round(aed*exchangeRates.AED_TO_EUR);document.getElementById('priceUSD').value=Math.round(aed*exchangeRates.AED_TO_USD)}else if(from==='USD'&&usd>0){document.getElementById('priceEUR').value=Math.round(usd*exchangeRates.USD_TO_EUR);document.getElementById('priceAED').value=Math.round(usd*exchangeRates.USD_TO_AED)}else if(from==='EUR'&&eur>0){document.getElementById('priceAED').value=Math.round(eur*exchangeRates.EUR_TO_AED);document.getElementById('priceUSD').value=Math.round(eur*exchangeRates.EUR_TO_USD)}}async function analyzeVehicle(){if(uploadedImages.length===0)return;document.getElementById('loading').style.display='block';document.getElementById('vehicleResults').style.display='none';try{const response=await fetch('/api/analyze-vehicle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({images:uploadedImages})});const data=await response.json();if(!response.ok||data.error){alert('Analysis error: '+(data.error||'Unknown error'));document.getElementById('loading').style.display='none';return}vehicleData=data;document.getElementById('edit_marca').value=data.marca||'';document.getElementById('edit_model').value=data.model||'';document.getElementById('edit_year').value=data.an_fabricatie||'2020';document.getElementById('edit_engine').value=data.motor_capacitate||'2.0L';document.getElementById('edit_fuel').value=data.combustibil||'benzina';document.getElementById('edit_co2').value=data.emisii_co2||'180';document.getElementById('vehicleResults').style.display='block';document.getElementById('vehicleResults').scrollIntoView({behavior:'smooth',block:'start'});selectShipping('roro')}catch(error){alert('Failed: '+error.message)}finally{document.getElementById('loading').style.display='none'}}async function calculateCosts(){const price=parseFloat(document.getElementById('priceEUR').value);if(!price||price<=0){alert('Enter EUR price');return}const marca=document.getElementById('edit_marca').value||'Unknown';const model=document.getElementById('edit_model').value||'Unknown';const year=parseInt(document.getElementById('edit_year').value)||2020;const engine=document.getElementById('edit_engine').value||'2.0L';const fuel=document.getElementById('edit_fuel').value||'benzina';const co2=parseInt(document.getElementById('edit_co2').value)||180;const dimensions={length:parseFloat(document.getElementById('dim_length').value)||4.5,width:parseFloat(document.getElementById('dim_width').value)||1.8,height:parseFloat(document.getElementById('dim_height').value)||1.5,weight:parseFloat(document.getElementById('dim_weight').value)||1500};document.getElementById('loading').style.display='block';try{const response=await fetch('/api/calculate-costs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vehicle_price:price,marca:marca,model:model,year:year,engine:engine,fuel_type:fuel,co2:co2,shipping_method:selectedShipping,dimensions:dimensions})});calculatedCosts=await response.json();displayCosts(calculatedCosts);marketEstimate=calculatedCosts.market_estimate;displayProfitability(calculatedCosts);setTimeout(()=>{document.getElementById('costResults').scrollIntoView({behavior:'smooth',block:'start'})},300)}catch(error){alert('Calc failed: '+error.message)}finally{document.getElementById('loading').style.display='none'}}function displayCosts(costs){const fz=costs.free_zone;const std=costs.standard;const nbpm=costs.no_bpm;const ship=costs.shipping_details;document.getElementById('freeZoneCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+fz.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+fz.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Fees:</span><span>€'+(fz.port_fees+fz.free_zone_entry+fz.agent+fz.docs_insurance).toLocaleString()+'</span></div><div class="cost-total">€'+fz.total.toLocaleString()+'</div>';document.getElementById('standardCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+std.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+std.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Duty+VAT:</span><span>€'+(std.import_duty+std.vat).toLocaleString()+'</span></div><div class="cost-line"><span>BPM:</span><span>€'+std.bpm.toLocaleString()+'</span></div><div class="cost-total">€'+std.total.toLocaleString()+'</div>';document.getElementById('noBpmCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+nbpm.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+nbpm.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Duty+VAT:</span><span>€'+(nbpm.import_duty+nbpm.vat).toLocaleString()+'</span></div><div class="cost-line"><span>BPM:</span><span style="color:#28a745">€0</span></div><div class="cost-total" style="border:3px solid #28a745;padding:8px">€'+nbpm.total.toLocaleString()+'</div>';document.getElementById('shippingBreakdown').innerHTML='<h4 style="font-size:1em">'+ship.shipping_method+'</h4><div class="shipping-breakdown"><span>Base:</span><span>€'+ship.base_shipping.toLocaleString()+'</span></div><div class="shipping-breakdown"><span>Loading:</span><span>€'+ship.loading_fee.toLocaleString()+'</span></div><div class="shipping-breakdown"><span>Total:</span><span>€'+ship.total.toLocaleString()+'</span></div>';const best=costs.recommendation;document.querySelectorAll('.cost-card').forEach(c=>c.classList.remove('recommended'));if(best==='FREE ZONE')document.getElementById('freeZoneCard').classList.add('recommended');else if(best==='NO BPM')document.getElementById('noBpmCard').classList.add('recommended');else document.getElementById('standardCard').classList.add('recommended');document.getElementById('recommendation').innerHTML='<strong>'+costs.recommendation_text+'</strong><br><small>'+costs.savings_details+'</small>';document.getElementById('costResults').style.display='block'}function displayProfitability(costs){const est=costs.market_estimate;if(!est){document.getElementById('profitabilitySection').style.display='none';return}const noBpmCost=costs.no_bpm.total;const avgMarket=est.avg_price;const profit=avgMarket-noBpmCost;const profitPct=(profit/noBpmCost)*100;let colorClass='profit-low';if(profitPct>=21)colorClass='profit-high';else if(profitPct>=10)colorClass='profit-medium';document.getElementById('marketEstimate').innerHTML='<h3 style="font-size:1.1em">🤖 AI Market Intelligence</h3><p style="font-size:0.9em"><strong>'+document.getElementById('edit_marca').value+' '+document.getElementById('edit_model').value+'</strong></p><div style="margin:12px 0"><div class="profit-breakdown"><span>Range:</span><span>€'+est.min_price.toLocaleString()+'-'+est.max_price.toLocaleString()+'</span></div><div class="profit-breakdown"><span>Average:</span><span>€'+avgMarket.toLocaleString()+'</span></div></div>';document.getElementById('profitabilityCard').innerHTML='<div class="profitability-card '+colorClass+'"><h3 style="font-size:1.1em">💰 Profit (vs NO BPM)</h3><div class="profit-breakdown"><span>Market:</span><span>€'+avgMarket.toLocaleString()+'</span></div><div class="profit-breakdown"><span>Cost:</span><span>€'+noBpmCost.toLocaleString()+'</span></div><div class="profit-breakdown" style="font-size:1.2em;font-weight:bold;margin-top:12px"><span>Profit:</span><span>€'+profit.toLocaleString()+'</span></div><div class="profit-percentage">'+profitPct.toFixed(1)+'%</div></div>';document.getElementById('profitabilitySection').style.display='block'}function recalculateProfit(){const manual=parseFloat(document.getElementById('manualMarketPrice').value);if(!manual||!calculatedCosts)return;const noBpmCost=calculatedCosts.no_bpm.total;const profit=manual-noBpmCost;const profitPct=(profit/noBpmCost)*100;let colorClass='profit-low';if(profitPct>=21)colorClass='profit-high';else if(profitPct>=10)colorClass='profit-medium';document.getElementById('profitabilityCard').innerHTML='<div class="profitability-card '+colorClass+'"><h3 style="font-size:1.1em">💰 Profit (Manual)</h3><div class="profit-breakdown"><span>Market:</span><span>€'+manual.toLocaleString()+'</span></div><div class="profit-breakdown"><span>Cost:</span><span>€'+noBpmCost.toLocaleString()+'</span></div><div class="profit-breakdown" style="font-size:1.2em;font-weight:bold;margin-top:12px"><span>Profit:</span><span>€'+profit.toLocaleString()+'</span></div><div class="profit-percentage">'+profitPct.toFixed(1)+'%</div></div>'}</script></body></html>'''

@app.route('/api/exchange-rates')
def get_rates():
    rates = get_exchange_rates()
    return jsonify(rates)

@app.route('/api/analyze-vehicle', methods=['POST'])
def analyze_vehicle():
    """Analyze vehicle from images with better error handling"""
    if not client: 
        return jsonify({'error':'API Key not configured'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error':'No JSON data'}), 400
            
        images_data = data.get('images', [])
        if not images_data or len(images_data) == 0:
            return jsonify({'error':'No images provided'}), 400
        
        print(f"Analyzing vehicle with {len(images_data)} images...")
        
        img_full = images_data[0]
        
        if ',' in img_full:
            img = img_full.split(',')[1]
        else:
            img = img_full
        
        media_type = detect_image_type(img)
        print(f"Detected media type: {media_type}")
        
        msg = client.messages.create(
            model="claude-sonnet-4-20250514", 
            max_tokens=1000,
            messages=[{
                "role":"user",
                "content":[
                    {"type":"image","source":{"type":"base64","media_type":media_type,"data":img}},
                    {"type":"text","text":'Analizează vehiculul din imagine. Returnează DOAR un JSON valid, fără text suplimentar. Format: {"marca":"Toyota","model":"Corolla","an_fabricatie":"2018","motor_capacitate":"1.8L","combustibil":"benzina","emisii_co2":"120"}'}
                ]
            }]
        )
        
        response_text = msg.content[0].text.strip()
        print(f"Claude response: {response_text[:200]}...")
        
        json_match = re.search(r'\{[^}]*"marca"[^}]*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = re.sub(r'^```json\s*|\s*```$', '', response_text, flags=re.MULTILINE)
        
        json_str = json_str.strip()
        
        try:
            result = json.loads(json_str)
        except json.JSONDecodeError:
            print(f"JSON parse failed, attempting manual extraction from: {json_str}")
            result = {
                'marca': 'Unknown',
                'model': 'Unknown', 
                'an_fabricatie': '2020',
                'motor_capacitate': '2.0L',
                'combustibil': 'benzina',
                'emisii_co2': '180'
            }
        
        print(f"Successfully analyzed: {result.get('marca')} {result.get('model')}")
        return jsonify(result)
        
    except json.JSONDecodeError as e:
        error_msg = f"JSON parse error: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({'error': error_msg}), 500
    except Exception as e: 
        error_msg = f"Analysis error: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return jsonify({'error': error_msg}), 500

@app.route('/api/calculate-costs', methods=['POST'])
def costs():
    try:
        d = request.json
        vp = float(d.get('vehicle_price', 0))
        co2 = int(d.get('co2', 180))
        year = int(d.get('year', 2020))
        fuel = d.get('fuel_type', 'benzina')
        shipping_method = d.get('shipping_method', 'roro')
        dimensions = d.get('dimensions', {})
        
        vehicle_data = {
            'marca': d.get('marca', 'Unknown'),
            'model': d.get('model', 'Unknown'),
            'year': year,
            'engine': d.get('engine', '2.0L'),
            'fuel_type': fuel,
            'co2': co2
        }
        
        shipping = calculate_shipping_cost(shipping_method, dimensions)
        shipping_total = shipping['total']
        port_fees = 600
        
        free_zone = {
            'vehicle_price': vp, 'shipping': shipping_total,
            'port_fees': port_fees, 'free_zone_entry': 150,
            'handling': 200, 'agent': 200, 'docs_insurance': 250,
            'total': round(vp + shipping_total + port_fees + 950, 2)
        }
        
        import_duty = vp * 0.10
        vat = (vp + shipping_total + import_duty) * 0.21
        bpm = calculate_bpm(co2, year, fuel)
        
        standard = {
            'vehicle_price': vp, 'shipping': shipping_total,
            'port_fees': port_fees, 'import_duty': round(import_duty, 2),
            'vat': round(vat, 2), 'bpm': bpm,
            'agent': 350, 'docs_insurance': 200,
            'total': round(vp + shipping_total + port_fees + import_duty + vat + bpm + 550, 2)
        }
        
        no_bpm = {
            'vehicle_price': vp, 'shipping': shipping_total,
            'port_fees': port_fees, 'import_duty': round(import_duty, 2),
            'vat': round(vat, 2), 'bpm': 0,
            'agent': 350, 'docs_insurance': 200,
            'total': round(vp + shipping_total + port_fees + import_duty + vat + 550, 2)
        }
        
        totals = {'FREE ZONE': free_zone['total'], 'STANDARD': standard['total'], 'NO BPM': no_bpm['total']}
        best = min(totals, key=totals.get)
        worst = max(totals, key=totals.get)
        savings = totals[worst] - totals[best]
        
        market_estimate = estimate_market_price_ai(vehicle_data)
        
        return jsonify({
            'free_zone': free_zone,
            'standard': standard,
            'no_bpm': no_bpm,
            'shipping_details': shipping,
            'recommendation': best,
            'recommendation_text': f"✅ {best} is best",
            'savings_details': f"Save €{savings:,.0f}",
            'market_estimate': market_estimate
        })
        
    except Exception as e:
        print(f"Cost calculation error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
