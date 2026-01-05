from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import json
import re
import base64
import requests

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Exchange rate cache (refresh every hour in production)
exchange_rates_cache = {}

def get_exchange_rates():
    """Get real-time exchange rates from exchangerate-api.com"""
    global exchange_rates_cache
    try:
        # Free tier: 1500 requests/month
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
        # Fallback rates
        return {
            'EUR_TO_AED': 3.95,
            'EUR_TO_USD': 1.09,
            'AED_TO_EUR': 0.253,
            'USD_TO_EUR': 0.917,
            'AED_TO_USD': 0.272,
            'USD_TO_AED': 3.67,
            'timestamp': 'fallback'
        }

def detect_image_type(base64_string):
    """Detect image type from base64 string"""
    try:
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
    except:
        pass
    
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
    """Calculate Dutch BPM tax with depreciation"""
    age = 2025 - year
    if age >= 5: 
        return 0
    
    bpm = 400
    if co2 > 82:
        bpm += (min(co2,140)-82)*80
        if co2 > 140: 
            bpm += (min(co2,180)-140)*120
        if co2 > 180: 
            bpm += (co2-180)*180
    
    if fuel_type.lower()=='diesel' and co2>82: 
        bpm += (co2-82)*90
    
    depreciation = min(age * 0.2, 1.0)
    return round(bpm * (1 - depreciation), 2)

def calculate_shipping_cost(container_type, vehicle_dimensions):
    """
    Calculate detailed shipping costs
    container_type: 'roro' or 'container_20ft' or 'container_40ft'
    vehicle_dimensions: {'length': m, 'width': m, 'height': m, 'weight': kg}
    """
    if container_type == 'roro':
        # RoRo (Roll-on/Roll-off) - cheapest for standard cars
        base_cost = 800
        # Size surcharge
        if vehicle_dimensions.get('length', 0) > 5:  # Over 5 meters
            base_cost += 200
        if vehicle_dimensions.get('height', 0) > 2:  # Over 2 meters (SUV)
            base_cost += 150
        
        return {
            'shipping_method': 'RoRo (Roll-on/Roll-off)',
            'base_shipping': base_cost,
            'loading_fee': 150,
            'unloading_fee': 150,
            'securing_fee': 50,
            'insurance': 100,
            'total': base_cost + 450
        }
    
    elif container_type == 'container_20ft':
        # 20ft container - for 1 standard vehicle
        return {
            'shipping_method': '20ft Container',
            'base_shipping': 1500,
            'loading_fee': 200,
            'unloading_fee': 200,
            'securing_fee': 100,
            'container_rental': 150,
            'insurance': 150,
            'total': 2300
        }
    
    elif container_type == 'container_40ft':
        # 40ft container - for 2 vehicles or 1 large vehicle
        return {
            'shipping_method': '40ft Container',
            'base_shipping': 2200,
            'loading_fee': 300,
            'unloading_fee': 300,
            'securing_fee': 150,
            'container_rental': 200,
            'insurance': 250,
            'total': 3400
        }
    
    # Default to RoRo
    return calculate_shipping_cost('roro', vehicle_dimensions)

@app.route('/')
def home():
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Vehicle Import Calculator v2.0</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}.container{max-width:1100px;margin:0 auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:10px;font-size:2em}.subtitle{text-align:center;color:#666;margin-bottom:30px}.version{text-align:center;color:#999;font-size:0.85em;margin-bottom:20px}.upload-zone{border:3px dashed #667eea;border-radius:15px;padding:40px;text-align:center;cursor:pointer;transition:all 0.3s;margin-bottom:30px}.upload-zone:hover{background:#f8f9ff}.upload-zone.dragover{background:#e8ebff;border-color:#764ba2}.image-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}.image-preview{max-width:100%;height:150px;object-fit:cover;border-radius:10px;border:2px solid #667eea}.image-slot{position:relative;text-align:center;padding:10px;background:#f8f9ff;border-radius:10px}.remove-image{position:absolute;top:5px;right:5px;background:red;color:white;border:none;border-radius:50%;width:25px;height:25px;cursor:pointer;font-weight:bold}.loading{text-align:center;padding:20px;display:none}.spinner{border:4px solid #f3f3f3;border-top:4px solid #667eea;border-radius:50%;width:50px;height:50px;animation:spin 1s linear infinite;margin:0 auto 10px}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}.result-item{background:#f8f9ff;padding:15px;border-radius:10px}.result-label{font-size:0.85em;color:#666;margin-bottom:5px}.edit-input{width:100%;padding:8px;border:2px solid #667eea;border-radius:5px;font-size:1em;margin-top:5px}button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:15px 30px;border-radius:10px;font-size:1.1em;cursor:pointer;width:100%;margin:10px 0}button:hover{transform:translateY(-2px)}button:disabled{opacity:0.5;cursor:not-allowed}.price-section{background:#f8f9ff;padding:20px;border-radius:10px;margin:20px 0}.price-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:15px;margin-bottom:20px}.price-input{width:100%;padding:15px;font-size:1.1em;border:2px solid #667eea;border-radius:10px}.shipping-section{background:#fff3cd;padding:20px;border-radius:10px;margin:20px 0}.shipping-options{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin:15px 0}.shipping-option{padding:15px;border:2px solid #ddd;border-radius:10px;cursor:pointer;text-align:center;transition:all 0.3s}.shipping-option:hover,.shipping-option.selected{border-color:#667eea;background:#f8f9ff}.dimension-inputs{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:15px 0}.dimension-input{padding:10px;border:2px solid #ddd;border-radius:5px}.cost-comparison{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:20px 0}.cost-card{background:white;border:2px solid #ddd;border-radius:15px;padding:20px}.cost-card.recommended{border-color:#28a745;background:#f0fff4}.cost-card h3{margin-bottom:15px;color:#667eea}.cost-line{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #eee}.cost-total{font-size:1.3em;font-weight:bold;color:#667eea;margin-top:10px}.recommendation{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;border-radius:15px;text-align:center;font-size:1.2em;margin:20px 0}.exchange-info{text-align:center;color:#666;font-size:0.85em;margin:10px 0;padding:10px;background:#fff;border-radius:5px}.shipping-details{background:#f8f9ff;padding:15px;border-radius:10px;margin:15px 0}.shipping-breakdown{display:grid;grid-template-columns:1fr auto;gap:10px;margin:10px 0;font-size:0.9em}.alert{padding:15px;border-radius:10px;margin:20px 0}.alert-info{background:#d1ecf1;border:1px solid #bee5eb;color:#0c5460}</style></head><body><div class="container"><h1>🚗 Vehicle Import Calculator</h1><p class="subtitle">Dubai → Rotterdam → EU | AI-Powered Analysis</p><p class="version">v2.0 - Multi-Image | Real-Time Rates | Detailed Shipping</p><div class="upload-zone" id="uploadZone"><p>📸 Upload up to 4 vehicle photos (JPG, PNG, WEBP, AVIF)</p><p style="font-size:0.9em;color:#666;margin-top:10px">Click or drag & drop • Best results: front, side, rear, interior</p><input type="file" id="fileInput" accept="image/*" multiple style="display:none"></div><div class="image-grid" id="imageGrid"></div><div class="loading" id="loading"><div class="spinner"></div><p>Analyzing vehicle with Claude AI...</p></div><div id="vehicleResults" style="display:none"><h2>Vehicle Analysis (Editable)</h2><div class="result-grid"><div class="result-item"><div class="result-label">Make & Model</div><input type="text" id="edit_marca" class="edit-input" placeholder="Make"><input type="text" id="edit_model" class="edit-input" placeholder="Model" style="margin-top:5px"></div><div class="result-item"><div class="result-label">Year</div><input type="number" id="edit_year" class="edit-input" placeholder="2020"></div><div class="result-item"><div class="result-label">Engine</div><input type="text" id="edit_engine" class="edit-input" placeholder="2.0L"></div><div class="result-item"><div class="result-label">Fuel Type</div><select id="edit_fuel" class="edit-input"><option value="benzina">Benzina</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option></select></div><div class="result-item"><div class="result-label">CO2 (g/km)</div><input type="number" id="edit_co2" class="edit-input" placeholder="180"></div></div><div class="shipping-section"><h3>🚢 Shipping Method</h3><div class="shipping-options"><div class="shipping-option" data-method="roro" onclick="selectShipping('roro')"><strong>RoRo</strong><p style="font-size:0.85em;margin-top:5px">Roll-on/Roll-off<br>Cheapest option</p></div><div class="shipping-option" data-method="container_20ft" onclick="selectShipping('container_20ft')"><strong>20ft Container</strong><p style="font-size:0.85em;margin-top:5px">1 standard vehicle<br>More secure</p></div><div class="shipping-option" data-method="container_40ft" onclick="selectShipping('container_40ft')"><strong>40ft Container</strong><p style="font-size:0.85em;margin-top:5px">2 vehicles or 1 large<br>Best for SUVs</p></div></div><h4 style="margin:15px 0 10px">Vehicle Dimensions (Optional - for accurate shipping cost)</h4><div class="dimension-inputs"><input type="number" id="dim_length" class="dimension-input" placeholder="Length (m)" step="0.1"><input type="number" id="dim_width" class="dimension-input" placeholder="Width (m)" step="0.1"><input type="number" id="dim_height" class="dimension-input" placeholder="Height (m)" step="0.1"><input type="number" id="dim_weight" class="dimension-input" placeholder="Weight (kg)"></div></div><div class="price-section"><h3>💰 Purchase Price (Enter in any currency)</h3><div class="price-grid"><div><label style="font-size:0.9em;color:#666">Dubai Price (AED)</label><input type="number" id="priceAED" class="price-input" placeholder="0" oninput="convertCurrency('AED')"></div><div><label style="font-size:0.9em;color:#666">Dubai Price (USD)</label><input type="number" id="priceUSD" class="price-input" placeholder="0" oninput="convertCurrency('USD')"></div><div><label style="font-size:0.9em;color:#666">Dubai Price (EUR)</label><input type="number" id="priceEUR" class="price-input" placeholder="0" oninput="convertCurrency('EUR')"></div></div><div class="exchange-info" id="exchangeInfo">Loading exchange rates...</div><button onclick="calculateCosts()">Calculate Import Costs</button></div></div><div id="costResults" style="display:none"><h2>💶 Cost Analysis (EUR)</h2><div class="alert alert-info"><strong>📊 Three Import Scenarios:</strong> FREE ZONE (tax-free) | STANDARD (with BPM) | NO BPM (5+ years old)</div><div class="cost-comparison"><div class="cost-card" id="freeZoneCard"><h3>🆓 FREE ZONE</h3><div id="freeZoneCosts"></div></div><div class="cost-card" id="standardCard"><h3>📋 STANDARD</h3><div id="standardCosts"></div></div><div class="cost-card" id="noBpmCard"><h3>🎯 NO BPM</h3><div id="noBpmCosts"></div></div></div><div class="shipping-details" id="shippingBreakdown"></div><div class="recommendation" id="recommendation"></div></div></div><script>let vehicleData={};let uploadedImages=[];let selectedShipping='roro';let exchangeRates={};const MAX_IMAGES=4;const uploadZone=document.getElementById('uploadZone');const fileInput=document.getElementById('fileInput');const imageGrid=document.getElementById('imageGrid');uploadZone.onclick=()=>fileInput.click();uploadZone.ondragover=(e)=>{e.preventDefault();uploadZone.classList.add('dragover')};uploadZone.ondragleave=()=>uploadZone.classList.remove('dragover');uploadZone.ondrop=(e)=>{e.preventDefault();uploadZone.classList.remove('dragover');handleFiles(e.dataTransfer.files)};fileInput.onchange=(e)=>handleFiles(e.target.files);function handleFiles(files){if(uploadedImages.length>=MAX_IMAGES){alert('Maximum 4 images allowed');return}Array.from(files).slice(0,MAX_IMAGES-uploadedImages.length).forEach(file=>{if(!file.type.startsWith('image/')){alert('Only images allowed');return}const reader=new FileReader();reader.onload=(e)=>{uploadedImages.push(e.target.result);displayImages();if(uploadedImages.length===1){analyzeVehicle()}};reader.readAsDataURL(file)})}function displayImages(){imageGrid.innerHTML='';uploadedImages.forEach((img,idx)=>{const slot=document.createElement('div');slot.className='image-slot';slot.innerHTML='<img src="'+img+'" class="image-preview"><button class="remove-image" onclick="removeImage('+idx+')">×</button><p style="font-size:0.8em;margin-top:5px">Photo '+(idx+1)+'</p>';imageGrid.appendChild(slot)})}function removeImage(idx){uploadedImages.splice(idx,1);displayImages()}function selectShipping(method){selectedShipping=method;document.querySelectorAll('.shipping-option').forEach(el=>el.classList.remove('selected'));document.querySelector('[data-method="'+method+'"]').classList.add('selected')}async function loadExchangeRates(){try{const response=await fetch('/api/exchange-rates');exchangeRates=await response.json();const info=document.getElementById('exchangeInfo');info.innerHTML='💱 Live rates: 1 EUR = '+exchangeRates.EUR_TO_AED.toFixed(2)+' AED | 1 EUR = '+exchangeRates.EUR_TO_USD.toFixed(2)+' USD<br><small>Updated: '+new Date(exchangeRates.timestamp).toLocaleString()+'</small>'}catch(e){console.error('Exchange rates error:',e)}}loadExchangeRates();function convertCurrency(from){const aed=parseFloat(document.getElementById('priceAED').value)||0;const usd=parseFloat(document.getElementById('priceUSD').value)||0;const eur=parseFloat(document.getElementById('priceEUR').value)||0;if(from==='AED'&&aed>0){document.getElementById('priceEUR').value=Math.round(aed*exchangeRates.AED_TO_EUR);document.getElementById('priceUSD').value=Math.round(aed*exchangeRates.AED_TO_USD)}else if(from==='USD'&&usd>0){document.getElementById('priceEUR').value=Math.round(usd*exchangeRates.USD_TO_EUR);document.getElementById('priceAED').value=Math.round(usd*exchangeRates.USD_TO_AED)}else if(from==='EUR'&&eur>0){document.getElementById('priceAED').value=Math.round(eur*exchangeRates.EUR_TO_AED);document.getElementById('priceUSD').value=Math.round(eur*exchangeRates.EUR_TO_USD)}}async function analyzeVehicle(){if(uploadedImages.length===0)return;document.getElementById('loading').style.display='block';document.getElementById('vehicleResults').style.display='none';try{const response=await fetch('/api/analyze-vehicle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({images:uploadedImages})});vehicleData=await response.json();if(vehicleData.error){alert('Error: '+vehicleData.error);return}document.getElementById('edit_marca').value=vehicleData.marca||'';document.getElementById('edit_model').value=vehicleData.model||'';document.getElementById('edit_year').value=vehicleData.an_fabricatie||'2020';document.getElementById('edit_engine').value=vehicleData.motor_capacitate||'2.0L';document.getElementById('edit_fuel').value=vehicleData.combustibil||'benzina';document.getElementById('edit_co2').value=vehicleData.emisii_co2||'180';document.getElementById('vehicleResults').style.display='block';selectShipping('roro')}catch(error){alert('Failed: '+error.message)}finally{document.getElementById('loading').style.display='none'}}async function calculateCosts(){const price=parseFloat(document.getElementById('priceEUR').value);if(!price||price<=0){alert('Enter valid EUR price');return}const co2=parseInt(document.getElementById('edit_co2').value)||180;const year=parseInt(document.getElementById('edit_year').value)||2020;const fuel=document.getElementById('edit_fuel').value||'benzina';const dimensions={length:parseFloat(document.getElementById('dim_length').value)||4.5,width:parseFloat(document.getElementById('dim_width').value)||1.8,height:parseFloat(document.getElementById('dim_height').value)||1.5,weight:parseFloat(document.getElementById('dim_weight').value)||1500};const response=await fetch('/api/calculate-costs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vehicle_price:price,co2:co2,year:year,fuel_type:fuel,shipping_method:selectedShipping,dimensions:dimensions})});const costs=await response.json();displayCosts(costs)}function displayCosts(costs){const fz=costs.free_zone;const std=costs.standard;const nbpm=costs.no_bpm;const ship=costs.shipping_details;document.getElementById('freeZoneCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+fz.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+fz.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Port Fees:</span><span>€'+fz.port_fees.toLocaleString()+'</span></div><div class="cost-line"><span>Free Zone:</span><span>€'+fz.free_zone_entry.toLocaleString()+'</span></div><div class="cost-line"><span>Agent:</span><span>€'+fz.agent.toLocaleString()+'</span></div><div class="cost-line"><span>Docs:</span><span>€'+fz.docs_insurance.toLocaleString()+'</span></div><div class="cost-total">TOTAL: €'+fz.total.toLocaleString()+'</div>';document.getElementById('standardCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+std.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+std.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Duty (10%):</span><span>€'+std.import_duty.toLocaleString()+'</span></div><div class="cost-line"><span>VAT (21%):</span><span>€'+std.vat.toLocaleString()+'</span></div><div class="cost-line"><span>BPM:</span><span>€'+std.bpm.toLocaleString()+'</span></div><div class="cost-line"><span>Agent:</span><span>€'+std.agent.toLocaleString()+'</span></div><div class="cost-total">TOTAL: €'+std.total.toLocaleString()+'</div>';document.getElementById('noBpmCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+nbpm.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+nbpm.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Duty (10%):</span><span>€'+nbpm.import_duty.toLocaleString()+'</span></div><div class="cost-line"><span>VAT (21%):</span><span>€'+nbpm.vat.toLocaleString()+'</span></div><div class="cost-line"><span>BPM:</span><span style="color:#28a745">€0</span></div><div class="cost-line"><span>Agent:</span><span>€'+nbpm.agent.toLocaleString()+'</span></div><div class="cost-total">TOTAL: €'+nbpm.total.toLocaleString()+'</div>';document.getElementById('shippingBreakdown').innerHTML='<h4>🚢 Shipping Breakdown ('+ship.shipping_method+')</h4><div class="shipping-breakdown"><span>Base Shipping:</span><span>€'+ship.base_shipping.toLocaleString()+'</span></div><div class="shipping-breakdown"><span>Loading Fee:</span><span>€'+ship.loading_fee.toLocaleString()+'</span></div><div class="shipping-breakdown"><span>Unloading Fee:</span><span>€'+ship.unloading_fee.toLocaleString()+'</span></div><div class="shipping-breakdown"><span>Securing/Lashing:</span><span>€'+ship.securing_fee.toLocaleString()+'</span></div>'+(ship.container_rental?'<div class="shipping-breakdown"><span>Container Rental:</span><span>€'+ship.container_rental.toLocaleString()+'</span></div>':'')+'<div class="shipping-breakdown"><span>Marine Insurance:</span><span>€'+ship.insurance.toLocaleString()+'</span></div><div class="shipping-breakdown" style="border-top:2px solid #667eea;margin-top:10px;padding-top:10px;font-weight:bold"><span>Total Shipping:</span><span>€'+ship.total.toLocaleString()+'</span></div>';const bestOption=costs.recommendation;if(bestOption==='FREE ZONE'){document.getElementById('freeZoneCard').classList.add('recommended')}else if(bestOption==='NO BPM'){document.getElementById('noBpmCard').classList.add('recommended')}else{document.getElementById('standardCard').classList.add('recommended')}document.getElementById('recommendation').innerHTML='<strong>'+costs.recommendation_text+'</strong><br><small>'+costs.savings_details+'</small>';document.getElementById('costResults').style.display='block'}</script></body></html>'''

@app.route('/api/exchange-rates')
def get_rates():
    """Get current exchange rates"""
    rates = get_exchange_rates()
    return jsonify(rates)

@app.route('/api/analyze-vehicle', methods=['POST'])
def analyze_vehicle():
    """Analyze vehicle from multiple images"""
    if not client: 
        return jsonify({'error':'API Key not configured'}), 500
    
    try:
        images_data = request.json.get('images', [])
        if not images_data:
            return jsonify({'error':'No images provided'}), 400
        
        # Use first image for analysis (or combine multiple in future)
        img_full = images_data[0]
        img = img_full.split(',')[1] if ',' in img_full else img_full
        media_type = detect_image_type(img)
        
        # Analyze with Claude Vision
        msg = client.messages.create(
            model="claude-sonnet-4-20250514", 
            max_tokens=1000,
            messages=[{
                "role":"user",
                "content":[
                    {"type":"image","source":{"type":"base64","media_type":media_type,"data":img}},
                    {"type":"text","text":'Analizează vehiculul și returnează doar JSON fără text suplimentar: {"marca":"","model":"","an_fabricatie":"2020","motor_capacitate":"2.0L","combustibil":"benzina","emisii_co2":"180"}'}
                ]
            }]
        )
        
        txt = re.sub(r'^```json\s*|\s*```$','',msg.content[0].text.strip(),flags=re.MULTILINE)
        result = json.loads(txt)
        
        # If multiple images, could analyze additional details from other angles
        # For now, return single analysis
        return jsonify(result)
        
    except Exception as e: 
        print(f"Error: {e}")
        return jsonify({'error':str(e)}), 500

@app.route('/api/calculate-costs', methods=['POST'])
def costs():
    """Calculate detailed import costs with three scenarios"""
    try:
        d = request.json
        vp = float(d.get('vehicle_price', 0))
        co2 = int(d.get('co2', 180))
        year = int(d.get('year', 2020))
        fuel = d.get('fuel_type', 'benzina')
        shipping_method = d.get('shipping_method', 'roro')
        dimensions = d.get('dimensions', {})
        
        # Get detailed shipping costs
        shipping = calculate_shipping_cost(shipping_method, dimensions)
        shipping_total = shipping['total']
        
        # Port and handling fees
        port_fees = 600
        
        # FREE ZONE scenario (no taxes)
        free_zone = {
            'vehicle_price': vp,
            'shipping': shipping_total,
            'port_fees': port_fees,
            'free_zone_entry': 150,
            'handling': 200,
            'agent': 200,
            'docs_insurance': 250,
            'total': round(vp + shipping_total + port_fees + 150 + 200 + 200 + 250, 2)
        }
        
        # STANDARD scenario (with BPM)
        import_duty = vp * 0.10
        vat = (vp + shipping_total + import_duty) * 0.21
        bpm = calculate_bpm(co2, year, fuel)
        
        standard = {
            'vehicle_price': vp,
            'shipping': shipping_total,
            'port_fees': port_fees,
            'import_duty': round(import_duty, 2),
            'vat': round(vat, 2),
            'bpm': bpm,
            'agent': 350,
            'docs_insurance': 200,
            'total': round(vp + shipping_total + port_fees + import_duty + vat + bpm + 350 + 200, 2)
        }
        
        # NO BPM scenario (5+ years or special exemption)
        no_bpm = {
            'vehicle_price': vp,
            'shipping': shipping_total,
            'port_fees': port_fees,
            'import_duty': round(import_duty, 2),
            'vat': round(vat, 2),
            'bpm': 0,
            'agent': 350,
            'docs_insurance': 200,
            'total': round(vp + shipping_total + port_fees + import_duty + vat + 0 + 350 + 200, 2)
        }
        
        # Determine best option
        totals = {
            'FREE ZONE': free_zone['total'],
            'STANDARD': standard['total'],
            'NO BPM': no_bpm['total']
        }
        
        best = min(totals, key=totals.get)
        worst = max(totals, key=totals.get)
        savings = totals[worst] - totals[best]
        
        return jsonify({
            'free_zone': free_zone,
            'standard': standard,
            'no_bpm': no_bpm,
            'shipping_details': shipping,
            'recommendation': best,
            'recommendation_text': f"✅ {best} is the most economical option",
            'savings_details': f"Save €{savings:,.0f} vs. {worst} route"
        })
        
    except Exception as e:
        print(f"Cost calculation error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
