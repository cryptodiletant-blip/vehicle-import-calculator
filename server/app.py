from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import anthropic
import os
import base64
import json
import re

app = Flask(__name__, template_folder='../templates')
CORS(app)

# API Key - Replit va adăuga asta în Secrets
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# Initialize Anthropic client
if ANTHROPIC_API_KEY:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    def calculate_bpm(co2, year, fuel_type):
        """
        Calculate BPM (Dutch vehicle registration tax)
        BPM = base + progressive rates based on CO2 + diesel surcharge
        Depreciation: 20% per year, 100% after 5 years
        """
        current_year = 2025
        age = current_year - year

        # 100% depreciation after 5 years = 0 BPM
        if age >= 5:
            return 0

        # Base BPM
        bpm_gross = 400

        # Progressive rates per gram CO2 above 82 g/km
        if co2 > 82:
            if co2 <= 140:
                bpm_gross += (co2 - 82) * 80
            elif co2 <= 180:
                bpm_gross += (140 - 82) * 80 + (co2 - 140) * 120
            else:
                bpm_gross += (140 - 82) * 80 + (180 - 140) * 120 + (co2 - 180) * 180

        # Diesel surcharge
        if fuel_type.lower() == 'diesel' and co2 > 82:
            bpm_gross += (co2 - 82) * 90

        # Apply depreciation
        depreciation = min(age * 0.20, 1.0)
        bpm_net = bpm_gross * (1 - depreciation)

        return round(bpm_net, 2)
        @app.route('/api/analyze-vehicle', methods=['POST'])
        def analyze_vehicle():
            """Analyze vehicle from uploaded photo using Claude Vision API"""
            try:
                if not ANTHROPIC_API_KEY:
                    return jsonify({'error': 'API Key not configured. Add ANTHROPIC_API_KEY in Secrets.'}), 500

                data = request.json
                image_data = data.get('image')

                if not image_data:
                    return jsonify({'error': 'No image provided'}), 400

                # Remove data URL prefix if present
                if ',' in image_data:
                    image_data = image_data.split(',')[1]

                # Prompt for Claude Vision
                prompt = """Analizează această imagine de vehicul și extrage următoarele informații în format JSON:

        {
          "marca": "marca exactă (ex: Jeep, Mercedes-Benz, BMW)",
          "model": "model exact (ex: Wrangler Unlimited, A35 AMG, X5)",
          "an_fabricatie": "an sau interval (ex: 2020, 2018-2020)",
          "motor_capacitate": "capacitate motor din badge-uri (ex: 2.0T, 3.6L, 2.0d)",
          "combustibil": "benzina/diesel/hybrid/electric",
          "trim": "nivel echipare (ex: Sahara, Rubicon, Sport, AMG, M Sport)",
          "emisii_co2": "estimare CO2 g/km (ex: 180, 243, 150)",
          "stare_generala": "descriere scurtă stare și daune vizibile",
          "modificari": "modificări aftermarket vizibile",
          "confidence": "scor încredere 0-100%",
          "intrebari_clarificare": ["întrebare 1", "întrebare 2"],
          "recomandari_poze": ["tip poză 1", "tip poză 2"]
        }

        Răspunde DOAR cu JSON valid, fără text suplimentar."""

                # Call Claude API
                message = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1000,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }]
                )

                # Extract JSON from response
                response_text = message.content[0].text

                # Try to parse JSON (handle markdown code blocks)
                try:
                    # Remove markdown code blocks if present
                    json_text = re.sub(r'^```json\s*|\s*```$', '', response_text.strip(), flags=re.MULTILINE)
                    vehicle_data = json.loads(json_text)
                except json.JSONDecodeError:
                    # Fallback: try to extract JSON using regex
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        vehicle_data = json.loads(json_match.group())
                    else:
                        return jsonify({'error': 'Failed to parse AI response', 'raw': response_text}), 500

                return jsonify(vehicle_data)

            except Exception as e:
                return jsonify({'error': str(e)}), 500
                @app.route('/api/clarify-vehicle', methods=['POST'])
                def clarify_vehicle():
                    """Update vehicle analysis with user-provided clarifications"""
                    try:
                        data = request.json
                        vehicle_data = data.get('vehicle_data', {})
                        user_answers = data.get('answers', {})

                        # Merge user answers into vehicle data
                        for key, value in user_answers.items():
                            if value:  # Only update if user provided a value
                                vehicle_data[key] = value

                        # Increase confidence after clarification
                        if 'confidence' in vehicle_data:
                            current_conf = int(vehicle_data['confidence'].replace('%', ''))
                            vehicle_data['confidence'] = f"{min(current_conf + 20, 95)}%"

                        return jsonify(vehicle_data)

                    except Exception as e:
                        return jsonify({'error': str(e)}), 500


                @app.route('/api/calculate-costs', methods=['POST'])
                def calculate_costs():
                    """Calculate FREE ZONE vs STANDARD import costs"""
                    try:
                        data = request.json
                        vehicle_price = float(data.get('vehicle_price', 0))
                        co2 = int(data.get('co2', 180))
                        year = int(data.get('year', 2020))
                        fuel_type = data.get('fuel_type', 'benzina')

                        # Determine shipping cost (container vs RoRo)
                        container_shipping = data.get('container', False)
                        shipping_cost = 1800 if container_shipping else 1000

                        # FIXED COSTS (same for both scenarios)
                        port_fees = 600
                        docs_insurance = 250

                        # FREE ZONE SCENARIO
                        free_zone_entry = 150
                        free_zone_handling = 200
                        free_zone_agent = 200

                        free_zone_total = (
                            vehicle_price + 
                            shipping_cost + 
                            port_fees + 
                            free_zone_entry + 
                            free_zone_handling + 
                            free_zone_agent + 
                            docs_insurance
                        )

                        # STANDARD IMPORT SCENARIO
                        import_duty = vehicle_price * 0.10
                        vat_base = vehicle_price + shipping_cost + import_duty
                        vat = vat_base * 0.21
                        bpm = calculate_bpm(co2, year, fuel_type)
                        standard_agent = 350
                        standard_docs = 200

                        standard_total = (
                            vehicle_price + 
                            shipping_cost + 
                            port_fees + 
                            import_duty + 
                            vat + 
                            bpm + 
                            standard_agent + 
                            standard_docs
                        )

                        # RECOMMENDATION
                        savings = standard_total - free_zone_total
                        recommendation = "FREE ZONE" if savings > 1000 else "STANDARD"
                        recommendation_text = f"Recomandare: {recommendation} economisește €{savings:,.2f}"

                        if recommendation == "FREE ZONE":
                            recommendation_text += " (ideal pentru reexport în UE)"
                        else:
                            recommendation_text += " (pentru vânzare în NL/DE)"

                        return jsonify({
                            'free_zone': {
                                'vehicle_price': vehicle_price,
                                'shipping': shipping_cost,
                                'port_fees': port_fees,
                                'free_zone_entry': free_zone_entry,
                                'handling': free_zone_handling,
                                'agent': free_zone_agent,
                                'docs_insurance': docs_insurance,
                                'total': round(free_zone_total, 2)
                            },
                            'standard': {
                                'vehicle_price': vehicle_price,
                                'shipping': shipping_cost,
                                'port_fees': port_fees,
                                'import_duty': round(import_duty, 2),
                                'vat': round(vat, 2),
                                'bpm': bpm,
                                'agent': standard_agent,
                                'docs_insurance': standard_docs,
                                'total': round(standard_total, 2)
                            },
                            'recommendation': recommendation,
                            'recommendation_text': recommendation_text,
                            'savings': round(savings, 2)
                        })

                    except Exception as e:
                        return jsonify({'error': str(e)}), 500
                        @app.route('/', defaults={'path': ''})
                        @app.route('/<path:path>')
                        def serve(path):
                            """Serve React frontend"""
                            if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
                                return send_from_directory(app.static_folder, path)
                            else:
                                return send_from_directory(app.static_folder, 'index.html')


                        if __name__ == '__main__':
                            app.run(host='0.0.0.0', port=5000, debug=True