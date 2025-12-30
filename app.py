from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os
import json
import re
import base64

app = Flask(__name__)
CORS(app)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def detect_image_type(base64_string):
    try:
        img_data = base64.b64decode(base64_string[:30])
        if img_data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif img_data.startswith(b'\x89PNG'):
            return 'image/png'
        elif img_data.startswith(b'RIFF') and b'WEBP' in img_data:
            return 'image/webp'
        elif img_data.startswith(b'GIF'):
            return 'image/gif'
        elif b'ftypavif' in img_data or b'ftypavis' in img_data:
            return 'image/avif'
    except:
        pass
    return 'image/jpeg'

def calculate_bpm(co2, year, fuel_type):
    age = 2025 - year
    if age >= 5: return 0
    bpm = 400
    if co2 > 82:
        bpm += (min(co2,140)-82)*80
        if co2 > 140: bpm += (min(co2,180)-140)*120
        if co2 > 180: bpm += (co2-180)*180
    if fuel_type.lower()=='diesel' and co2>82: bpm += (co2-82)*90
    return round(bpm * (1 - min(age*0.2, 1.0)), 2)

@app.route('/')
def home():
    return '''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Vehicle Import Calculator</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}.container{max-width:900px;margin:0 auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.3)}h1{color:#667eea;text-align:center;margin-bottom:10px;font-size:2em}.subtitle{text-align:center;color:#666;margin-bottom:30px}.upload-zone{border:3px dashed #667eea;border-radius:15px;padding:40px;text-align:center;cursor:pointer;transition:all 0.3s;margin-bottom:30px}.upload-zone:hover{background:#f8f9ff}#imagePreview{max-width:100%;max-height:300px;margin:20px 0;border-radius:10px;display:none}.loading{text-align:center;padding:20px;display:none}.spinner{border:4px solid #f3f3f3;border-top:4px solid #667eea;border-radius:50%;width:50px;height:50px;animation:spin 1s linear infinite;margin:0 auto 10px}@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}.result-item{background:#f8f9ff;padding:15px;border-radius:10px}.result-label{font-size:0.85em;color:#666;margin-bottom:5px}.result-value{font-size:1em;font-weight:bold;color:#333}.edit-input{width:100%;padding:8px;border:2px solid #667eea;border-radius:5px;font-size:1em;margin-top:5px}button{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;border:none;padding:15px 30px;border-radius:10px;font-size:1.1em;cursor:pointer;width:100%;margin:10px 0}button:hover{transform:translateY(-2px)}.price-section{background:#f8f9ff;padding:20px;border-radius:10px;margin:20px 0}.price-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}.price-input{width:100%;padding:15px;font-size:1.2em;border:2px solid #667eea;border-radius:10px}.cost-comparison{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}.cost-card{background:white;border:2px solid #ddd;border-radius:15px;padding:20px}.cost-card.recommended{border-color:#28a745;background:#f0fff4}.cost-line{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #eee}.cost-total{font-size:1.3em;font-weight:bold;color:#667eea;margin-top:10px}.recommendation{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;border-radius:15px;text-align:center;font-size:1.2em;margin:20px 0}.exchange-rate{text-align:center;color:#666;font-size:0.9em;margin-top:10px}</style></head><body><div class="container"><h1>🚗 Vehicle Import Calculator</h1><p class="subtitle">Dubai → Rotterdam → EU | AI-Powered</p><div class="upload-zone" id="uploadZone"><p>📸 Click to upload vehicle photo (JPG, PNG, WEBP, AVIF)</p><input type="file" id="fileInput" accept="image/*" style="display:none"></div><img id="imagePreview"><div class="loading" id="loading"><div class="spinner"></div><p>Analyzing with Claude AI...</p></div><div id="vehicleResults" style="display:none"><h2>Vehicle Analysis (Editable)</h2><div class="result-grid"><div class="result-item"><div class="result-label">Make & Model</div><input type="text" id="edit_marca" class="edit-input" placeholder="Make"><input type="text" id="edit_model" class="edit-input" placeholder="Model" style="margin-top:5px"></div><div class="result-item"><div class="result-label">Year</div><input type="number" id="edit_year" class="edit-input" placeholder="2020"></div><div class="result-item"><div class="result-label">Engine</div><input type="text" id="edit_engine" class="edit-input" placeholder="2.0L"></div><div class="result-item"><div class="result-label">Fuel Type</div><select id="edit_fuel" class="edit-input"><option value="benzina">Benzina</option><option value="diesel">Diesel</option><option value="hybrid">Hybrid</option><option value="electric">Electric</option></select></div><div class="result-item"><div class="result-label">CO2 Emissions (g/km)</div><input type="number" id="edit_co2" class="edit-input" placeholder="180"></div></div><div class="price-section"><label><strong>Purchase Price:</strong></label><div class="price-grid"><div><label style="font-size:0.9em;color:#666">Dubai Price (AED)</label><input type="number" id="priceAED" class="price-input" placeholder="Enter AED" oninput="convertAEDtoEUR()"></div><div><label style="font-size:0.9em;color:#666">Dubai Price (EUR)</label><input type="number" id="priceEUR" class="price-input" placeholder="Enter EUR" oninput="convertEURtoAED()"></div></div><div class="exchange-rate">Exchange rate: 1 EUR = 3.95 AED (approx)</div><button onclick="calculateCosts()">Calculate Import Costs</button></div></div><div id="costResults" style="display:none"><h2>Cost Analysis (EUR)</h2><div class="cost-comparison"><div class="cost-card" id="freeZoneCard"><h3>🆓 FREE ZONE</h3><div id="freeZoneCosts"></div></div><div class="cost-card" id="standardCard"><h3>📋 STANDARD</h3><div id="standardCosts"></div></div></div><div class="recommendation" id="recommendation"></div></div></div><script>const AED_TO_EUR=0.253;const EUR_TO_AED=3.95;let vehicleData={};let imageBase64='';const uploadZone=document.getElementById('uploadZone');const fileInput=document.getElementById('fileInput');const imagePreview=document.getElementById('imagePreview');uploadZone.onclick=()=>fileInput.click();fileInput.onchange=(e)=>{const file=e.target.files[0];if(!file||!file.type.startsWith('image/')){alert('Upload image');return}const reader=new FileReader();reader.onload=(e)=>{imageBase64=e.target.result;imagePreview.src=imageBase64;imagePreview.style.display='block';analyzeVehicle()};reader.readAsDataURL(file)};function convertAEDtoEUR(){const aed=parseFloat(document.getElementById('priceAED').value);if(aed&&aed>0){document.getElementById('priceEUR').value=Math.round(aed*AED_TO_EUR)}}function convertEURtoAED(){const eur=parseFloat(document.getElementById('priceEUR').value);if(eur&&eur>0){document.getElementById('priceAED').value=Math.round(eur*EUR_TO_AED)}}async function analyzeVehicle(){document.getElementById('loading').style.display='block';document.getElementById('vehicleResults').style.display='none';try{const response=await fetch('/api/analyze-vehicle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:imageBase64})});vehicleData=await response.json();if(vehicleData.error){alert('Error: '+vehicleData.error);return}document.getElementById('edit_marca').value=vehicleData.marca||'';document.getElementById('edit_model').value=vehicleData.model||'';document.getElementById('edit_year').value=vehicleData.an_fabricatie||'2020';document.getElementById('edit_engine').value=vehicleData.motor_capacitate||'2.0L';document.getElementById('edit_fuel').value=vehicleData.combustibil||'benzina';document.getElementById('edit_co2').value=vehicleData.emisii_co2||'180';document.getElementById('vehicleResults').style.display='block'}catch(error){alert('Failed: '+error.message)}finally{document.getElementById('loading').style.display='none'}}async function calculateCosts(){const price=parseFloat(document.getElementById('priceEUR').value);if(!price||price<=0){alert('Enter valid EUR price');return}const co2=parseInt(document.getElementById('edit_co2').value)||180;const year=parseInt(document.getElementById('edit_year').value)||2020;const fuel=document.getElementById('edit_fuel').value||'benzina';const response=await fetch('/api/calculate-costs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({vehicle_price:price,co2:co2,year:year,fuel_type:fuel})});const costs=await response.json();const fz=costs.free_zone;const std=costs.standard;document.getElementById('freeZoneCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+fz.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Shipping:</span><span>€'+fz.shipping.toLocaleString()+'</span></div><div class="cost-line"><span>Total Fees:</span><span>€'+(fz.port_fees+fz.free_zone_entry+fz.agent+fz.docs_insurance).toLocaleString()+'</span></div><div class="cost-total">TOTAL: €'+fz.total.toLocaleString()+'</div>';document.getElementById('standardCosts').innerHTML='<div class="cost-line"><span>Vehicle:</span><span>€'+std.vehicle_price.toLocaleString()+'</span></div><div class="cost-line"><span>Duty+VAT:</span><span>€'+(std.import_duty+std.vat).toLocaleString()+'</span></div><div class="cost-line"><span>BPM:</span><span>€'+std.bpm.toLocaleString()+'</span></div><div class="cost-total">TOTAL: €'+std.total.toLocaleString()+'</div>';if(costs.recommendation==='FREE ZONE'){document.getElementById('freeZoneCard').classList.add('recommended')}else{document.getElementById('standardCard').classList.add('recommended')}document.getElementById('recommendation').innerHTML='<strong>'+costs.recommendation_text+'</strong>';document.getElementById('costResults').style.display='block'}</script></body></html>'''

@app.route('/api/analyze-vehicle', methods=['POST'])
def analyze_vehicle():
    if not client: return jsonify({'error':'API Key not configured'}), 500
    try:
        img_full = request.json.get('image','')
        img = img_full.split(',')[1] if ',' in img_full else img_full
        media_type = detect_image_type(img)
        msg = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=1000,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":media_type,"data":img}},
                {"type":"text","text":'Analizează vehiculul și returnează doar JSON fără text suplimentar: {"marca":"","model":"","an_fabricatie":"2020","motor_capacitate":"2.0L","combustibil":"benzina","emisii_co2":"180"}'}]}])
        txt = re.sub(r'^```json\s*|\s*```$','',msg.content[0].text.strip(),flags=re.MULTILINE)
        return jsonify(json.loads(txt))
    except Exception as e: return jsonify({'error':str(e)}), 500

@app.route('/api/calculate-costs', methods=['POST'])
def costs():
    d = request.json
    vp = float(d.get('vehicle_price',0))
    fz = vp+2400
    duty,vat = vp*0.1, (vp+1000+vp*0.1)*0.21
    bpm = calculate_bpm(int(d.get('co2',180)), int(d.get('year',2020)), d.get('fuel_type','benzina'))
    std = vp+1000+600+duty+vat+bpm+550
    sav = std-fz
    return jsonify({
        'free_zone':{'vehicle_price':vp,'shipping':1000,'port_fees':600,'free_zone_entry':150,'handling':200,'agent':200,'docs_insurance':250,'total':round(fz,2)},
        'standard':{'vehicle_price':vp,'shipping':1000,'port_fees':600,'import_duty':round(duty,2),'vat':round(vat,2),'bpm':bpm,'agent':350,'docs_insurance':200,'total':round(std,2)},
        'recommendation':"FREE ZONE" if sav>1000 else "STANDARD",
        'recommendation_text':f"{'FREE ZONE' if sav>1000 else 'STANDARD'} saves €{abs(sav):,.0f}",
        'savings':round(sav,2)})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
