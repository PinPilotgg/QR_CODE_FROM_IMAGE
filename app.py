from flask import Flask, request, jsonify, send_file
import cv2
import numpy as np
from PIL import Image
import easyocr
import qrcode
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from geopy.distance import geodesic
import io
import re
import os
import time
import uuid

app = Flask(__name__)
API_KEY = "2023etb011.subhadeep@students.iiests.ac.in"
reader = easyocr.Reader(['en'])

def extract_text_lines_from_image(image_path):
    pil_image = Image.open(image_path)
    open_cv_image = np.array(pil_image)
    open_cv_image = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2BGR)
    
    results = reader.readtext(image_path)
    text_lines = []
    
    for result in results:
        text = result[1]
        box = np.array(result[0], dtype=np.int32)
        cv2.polylines(open_cv_image, [box], isClosed=True, color=(0, 255, 0), thickness=2)
        cv2.putText(open_cv_image, text, (box[0][0], box[0][1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        text_lines.append(text)
    
    annotated_image_path = 'output.jpg'
    cv2.imwrite(annotated_image_path, open_cv_image)
    
    return text_lines

def identify_address_and_pincode(text_lines):
    address_line = ""
    pincode_line = ""
    
    for line in text_lines:
        if re.search(r'\b\d{6}\b', line):
            pincode_line = line
        else:
            address_line += line + " "
    
    address_line = address_line.strip()
    pincode = re.search(r'\b\d{6}\b', pincode_line)
    pincode = pincode.group() if pincode else ""
    
    return address_line, pincode

def get_lat_lng_from_google_maps(address):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    service = Service('./Chromedriver/chromedriver.exe')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.get("https://maps.google.com")
    time.sleep(2)
    
    search_box = driver.find_element(By.NAME, "q")
    search_box.send_keys(address)
    search_box.send_keys(Keys.RETURN)
    time.sleep(5)
    
    current_url = driver.current_url
    try:
        lat_lng = current_url.split("@")[1].split(",")[:2]
        latitude, longitude = lat_lng
        driver.quit()
        return float(latitude), float(longitude)
    except IndexError:
        driver.quit()
        return None, None

def find_nearest_post_office(pincode, address_coords):
    csv_file_path = './pincode (1).csv'
    df = pd.read_csv(csv_file_path)
    filtered_df = df[(df['Pincode'] == int(pincode)) & (df['Delivery'] == 'Delivery')]
    
    if filtered_df.empty:
        return None
    
    nearest_post_office = None
    min_distance = float('inf')
    
    for _, row in filtered_df.iterrows():
        post_office_coords = (row['Latitude'], row['Longitude'])
        distance = geodesic(address_coords, post_office_coords).kilometers
        if distance < min_distance:
            min_distance = distance
            nearest_post_office = row
    
    return nearest_post_office

def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    return img

@app.route('/upload_image', methods=['POST'])
def upload_image():
    api_key = request.headers.get('API-KEY')
    if not api_key or api_key != API_KEY:
        return jsonify({'error': 'Invalid or missing API key'}), 401

    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    image_file = request.files['image']
    image_path = './uploaded_image.jpeg'
    image_file.save(image_path)
    
    text_lines = extract_text_lines_from_image(image_path)
    address, pincode = identify_address_and_pincode(text_lines)
    
    if not address or not pincode:
        return jsonify({'error': 'Address or pincode not found'}), 400

    address_coords = get_lat_lng_from_google_maps(address)
    
    if address_coords is None:
        return jsonify({'error': 'Unable to get coordinates from Google Maps'}), 400

    nearest_post_office = find_nearest_post_office(pincode, address_coords)
    
    unique_id = str(uuid.uuid4())
    
    if nearest_post_office is not None:
        post_office_info = {
            'OfficeName': nearest_post_office['OfficeName'],
            'District': nearest_post_office['District'],
            'StateName': nearest_post_office['StateName'],
            'Latitude': nearest_post_office['Latitude'],
            'Longitude': nearest_post_office['Longitude']
        }
        qr_data = (
            f"Reference ID: {unique_id}\n"
            f"Address: {address}\n"
            f"Pincode: {pincode}\n"
            f"Post Office: {post_office_info['OfficeName']}\n"
            f"District: {post_office_info['District']}\n"
            f"State: {post_office_info['StateName']}\n"
            f"Coordinates: {post_office_info['Latitude']}, {post_office_info['Longitude']}"
        )
    else:
        qr_data = (
            f"Reference ID: {unique_id}\n"
            f"Address: {address}\n"
            f"Pincode: {pincode}\n"
            f"No nearby post office found."
        )
    
    qr_img = generate_qr_code(qr_data)

    qr_img_path = 'qr_code.png'
    qr_img.save(qr_img_path)
    
    return send_file(qr_img_path, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)
