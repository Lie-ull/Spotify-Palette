import os
import io
import json
import base64
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, render_template, redirect, session
from flask_cors import CORS
from dotenv import load_dotenv
from PIL import Image
from colorthief import ColorThief


load_dotenv('credentials.env')

app = Flask(__name__)
CORS(app)
app.secret_key = os.urandom(24)

# Spotify API credentials
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET', '')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'http://localhost:5000/callback')

# Routes

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/auth')
def auth():

    scope = 'user-read-currently-playing user-read-recently-played'
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'scope': scope,
        'redirect_uri': REDIRECT_URI,
        'show_dialog': True
    }
    auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback')
def callback():

    error = request.args.get('error')
    code = request.args.get('code')

    if error:
        return redirect('/limited')

    auth_options = {
        'url': 'https://accounts.spotify.com/api/token',
        'data': {
            'code': code,
            'redirect_uri': REDIRECT_URI,
            'grant_type': 'authorization_code',
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        },
        'headers': {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    }

    response = requests.post(auth_options['url'],
                          data=auth_options['data'],
                          headers=auth_options['headers'])
    token_info = response.json()

    # Store token in session
    session['access_token'] = token_info.get('access_token')

    return redirect('/app')

@app.route('/limited')
def limited_access():
    return render_template('limited.html')

#Gets an images width
def image_width(image):
    if 'width' in image:
        return image['width']
    else:
        return 0

#returns artists name
def get_artist_name(artists):
    artist_name = []
    for artist in artists:
        artist_name.append(artist['name'])
    final_artist = ', '.join(artist_name)
    return final_artist

@app.route('/limited-search')
def limited_search_album():
    """Search for an album on Spotify without requiring user authentication"""
    query = request.args.get('q')
    if query is None or query == "":
        return jsonify({"error": "No search query provided"}), 400

    auth_options = {
        'url': 'https://accounts.spotify.com/api/token',
        'data': {
            'grant_type': 'client_credentials'
        },
        'headers': {
            'Authorization': 'Basic ' + base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    }

    token_response = requests.post(auth_options['url'],
                                   data=auth_options['data'],
                                   headers=auth_options['headers'])
    token_info = token_response.json()
    app_token = token_info.get('access_token')

    # Use the app token to search spotify
    headers = {'Authorization': f"Bearer {app_token}"}
    response = requests.get(
        f"https://api.spotify.com/v1/search?q={query}&type=album&limit=1",
        headers=headers
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to search albums"}), response.status_code

    data = response.json()
    if 'albums' not in data:
        return jsonify({"error": "No albums found"}), 404
    if 'items' not in data['albums']:
        return jsonify({"error": "No albums found"}), 404
    if len(data['albums']['items']) == 0:
        return jsonify({"error": "No albums found"}), 404

    album = data['albums']['items'][0]
    album_id = album['id']

    # Get detailed album info
    album_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers)

    if album_response.status_code != 200:
        return jsonify({"error": "Failed to get album details"}), album_response.status_code

    album_data = album_response.json()

    # Get the largest image
    if 'images' not in album_data or len(album_data['images']) == 0:
        return jsonify({"error": "No artwork available"}), 404

    images = sorted(album_data['images'], key = image_width, reverse = True)
    image_url = images[0]['url']

    # extract colors
    palette = extract_colors(image_url)

    final_artist = get_artist_name(album_data['artists'])

    return jsonify({
        "album": {
            "name": album_data['name'],
            "artist": final_artist,
            "release_date": album_data['release_date'],
            "image_url": image_url
        },
        "colors": palette
    })




@app.route('/app')
def app_page():

    if 'access_token' not in session:
        return redirect('/auth')
    return render_template('app.html', token=session['access_token'])

@app.route('/current-track')
def get_current_track():

    if 'access_token' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    headers = {'Authorization': f"Bearer {session['access_token']}"}
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers)

    if response.status_code == 204:
        return jsonify({"error": "No track currently playing"}), 404

    if response.status_code != 200:
        return jsonify({"error": "Failed to get current track"}), response.status_code

    data = response.json()
    if 'item' not in data:
        return jsonify({"error": "No track information available"}), 404

    # get album details
    album_id = data['item']['album']['id']
    album_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers)

    if album_response.status_code != 200:
        return jsonify({"error": "Failed to get album details"}), album_response.status_code

    album_data = album_response.json()

    # Get the largest image
    if 'images' not in album_data or len(album_data['images']) == 0:
        return jsonify({"error": "No album artwork available"}), 404

    images = sorted(album_data['images'], key= image_width, reverse=True)
    image_url = images[0]['url']

    # Extract coloors
    palette = extract_colors(image_url)

    final_artist = get_artist_name(album_data['artists'])

    return jsonify({
        "track": {
            "name": data['item']['name'],
            "artist": final_artist,
            "album": album_data['name'],
            "release_date": album_data['release_date'],
            "image_url": image_url
        },
        "colors": palette
    })

@app.route('/search')
def search_album():
    """Search for an album on Spotify"""
    if 'access_token' not in session:
        return jsonify({"error": "Not authenticated"}), 401

    query = request.args.get('q')
    if query is None or query == "":
        return jsonify({"error": "No search query provided"}), 400

    headers = {'Authorization': f"Bearer {session['access_token']}"}
    response = requests.get(
        f"https://api.spotify.com/v1/search?q={query}&type=album&limit=1",
        headers=headers
    )

    if response.status_code != 200:
        return jsonify({"error": "Failed to search albums"}), response.status_code

    data = response.json()
    if 'albums' not in data:
        return jsonify({"error": "No albums found"}), 404
    if 'items' not in data['albums']:
        return jsonify({"error": "No albums found"}), 404
    if len(data['albums']['items']) == 0:
        return jsonify({"error": "No albums found"}), 404

    album = data['albums']['items'][0]
    album_id = album['id']

    # Get detailed album info
    album_response = requests.get(f"https://api.spotify.com/v1/albums/{album_id}", headers=headers)

    if album_response.status_code != 200:
        return jsonify({"error": "Failed to get album details"}), album_response.status_code

    album_data = album_response.json()

    # Get the largest image
    if 'images' not in album_data:
        return jsonify({"error": "No album artwork available"}), 404

    images = sorted(album_data['images'], key=image_width, reverse=True)
    image_url = images[0]['url']

    # extract colors
    palette = extract_colors(image_url)

    final_artist = get_artist_name(album_data['artists'])

    return jsonify({
        "album": {
            "name": album_data['name'],
            "artist": final_artist,
            "release_date": album_data['release_date'],
            "image_url": image_url
        },
        "colors": palette
    })

def rgb_to_hex(rgb_tuple):

    r = rgb_tuple[0]
    b = rgb_tuple[1]
    g = rgb_tuple[2]
    hex_color = '#%02x%02x%02x' % (r, g, b)
    return hex_color

def extract_colors(image_url, color_count=5):

    try:
        # Download the image
        response = requests.get(image_url)
        img = Image.open(io.BytesIO(response.content))

        # Save to a temporary file because ColorThief needs a file-like object
        temp_img = io.BytesIO()
        img.save(temp_img, format='PNG')
        temp_img.seek(0)

        # Extract the palette
        color_thief = ColorThief(temp_img)
        palette = color_thief.get_palette(color_count=color_count, quality=10)

        # Convert to hex codes
        hex_colors = []
        for rgb in palette:
            hex_color = rgb_to_hex(rgb)
            hex_colors.append(hex_color)
        return hex_colors

    except Exception as e:
        print(f"Error extracting colors: {e}")
        # Return some default colors in case of error
        return ["#4FB3BF", "#CD904D", "#1F1A3F", "#A0B5BE", "#8B4513"]

# Create necessary directories for templates
if not os.path.exists('templates'):
    os.makedirs('templates')

# Create HTML templates
with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Album Color Palette</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #121212;
            color: #ffffff;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            text-align: center;
        }
        .container {
            max-width: 600px;
            padding: 40px;
            background-color: #1e1e1e;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        }
        h1 {
            margin-bottom: 30px;
            font-size: 2.5rem;
        }
        p {
            margin-bottom: 30px;
            font-size: 1.1rem;
            color: #b3b3b3;
        }
        .login-button {
            background-color: #1DB954;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 30px;
            font-size: 1.1rem;
            cursor: pointer;
            transition: background-color 0.3s, transform 0.2s;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .login-button:hover {
            background-color: #1ed760;
            transform: scale(1.05);
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Spotify Album Color Palette</h1>
        <p>Extract dominant colors from your favorite album artwork or currently playing track.</p>
        <a href="/auth" class="login-button">Connect with Spotify</a>
    </div>
</body>
</html>
    ''')

with open('templates/app.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Album Color Palette</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #121212;
            color: #ffffff;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        h1 {
            margin-bottom: 30px;
        }

        .container {
            display: flex;
            flex-direction: column;
            align-items: center;
            max-width: 800px;
            width: 100%;
        }

        .search-container {
            width: 100%;
            margin-bottom: 30px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .search-box {
            display: flex;
            width: 100%;
            max-width: 500px;
        }

        input {
            flex-grow: 1;
            padding: 10px;
            border: none;
            border-radius: 4px 0 0 4px;
            font-size: 16px;
        }

        button {
            background-color: #1DB954;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            transition: background-color 0.3s;
        }

        .search-box button {
            border-radius: 0 4px 4px 0;
        }

        button:hover {
            background-color: #1ed760;
        }

        .result-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            width: 100%;
            margin-top: 20px;
        }

        .album-info {
            display: flex;
            flex-direction: column;
            align-items: center;
            margin-bottom: 20px;
        }

        .album-info img {
            width: 300px;
            height: 300px;
            margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
        }

        .album-details {
            text-align: center;
            margin-bottom: 20px;
        }

        .album-details h2 {
            margin-bottom: 5px;
        }

        .album-details p {
            margin: 5px 0;
            color: #b3b3b3;
        }

        .color-palette {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            margin-top: 20px;
            width: 100%;
        }

        .color-box {
            width: 120px;
            height: 120px;
            margin: 10px;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            align-items: center;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
            overflow: hidden;
        }

        .color-code {
            background-color: rgba(255, 255, 255, 0.85);
            width: 100%;
            padding: 8px 0;
            text-align: center;
            color: #333;
            font-weight: bold;
            font-family: monospace;
            font-size: 14px;
        }

        .loading {
            display: none;
            margin-top: 20px;
        }

        .spinner {
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top: 4px solid #1DB954;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .error-message {
            color: #ff5555;
            margin-top: 10px;
            text-align: center;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Spotify Album Color Palette</h1>

        <div class="search-container">
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search for an album...">
                <button id="search-button">Search</button>
            </div>
            <p>Or view your currently playing track:</p>
            <button id="current-button">Get Current Track</button>
        </div>

        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>Extracting colors...</p>
        </div>

        <div class="error-message" id="error-message"></div>

        <div class="result-container" id="result" style="display: none;">
            <div class="album-info">
                <img id="album-cover" src="" alt="Album cover">
                <div class="album-details">
                    <h2 id="album-name"></h2>
                    <p id="artist-name"></p>
                    <p id="release-date"></p>
                </div>
            </div>

            <div class="color-palette" id="color-palette"></div>
        </div>
    </div>

    <script>
        // Get access token passed from Flask
        const token = "{{ token }}";

        // DOM elements
        const searchInput = document.getElementById('search-input');
        const searchButton = document.getElementById('search-button');
        const currentButton = document.getElementById('current-button');
        const resultSection = document.getElementById('result');
        const loadingSection = document.getElementById('loading');
        const errorMessage = document.getElementById('error-message');

        const albumCover = document.getElementById('album-cover');
        const albumName = document.getElementById('album-name');
        const artistName = document.getElementById('artist-name');
        const releaseDate = document.getElementById('release-date');
        const colorPalette = document.getElementById('color-palette');

        // Event listeners
        searchButton.addEventListener('click', searchAlbums);
        currentButton.addEventListener('click', getCurrentTrack);
        searchInput.addEventListener('keyup', function(event) {
            if (event.key === 'Enter') {
                searchAlbums();
            }
        });

        function searchAlbums() {
            const query = searchInput.value.trim();
            if (!query) return;

            loadingSection.style.display = 'flex';
            resultSection.style.display = 'none';
            errorMessage.style.display = 'none';

            fetch(`/search?q=${encodeURIComponent(query)}`)
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Failed to search albums');
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    displayAlbumInfo(data);
                })
                .catch(error => {
                    showError(error.message);
                });
        }

        function getCurrentTrack() {
            loadingSection.style.display = 'flex';
            resultSection.style.display = 'none';
            errorMessage.style.display = 'none';

            fetch('/current-track')
                .then(response => {
                    if (!response.ok) {
                        return response.json().then(data => {
                            throw new Error(data.error || 'Failed to get current track');
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    displayTrackInfo(data);
                })
                .catch(error => {
                    showError(error.message);
                });
        }

        function displayAlbumInfo(data) {
            // Set album details
            albumName.textContent = data.album.name;
            artistName.textContent = data.album.artist;
            releaseDate.textContent = `Released: ${formatDate(data.album.release_date)}`;
            albumCover.src = data.album.image_url;

            // Create color palette
            createColorPalette(data.colors);

            // Show results
            loadingSection.style.display = 'none';
            resultSection.style.display = 'flex';
        }

        function displayTrackInfo(data) {
            // Set track details
            albumName.textContent = data.track.album;
            artistName.textContent = data.track.artist;
            releaseDate.textContent = `Track: ${data.track.name}`;
            albumCover.src = data.track.image_url;

            // Create color palette
            createColorPalette(data.colors);

            // Show results
            loadingSection.style.display = 'none';
            resultSection.style.display = 'flex';
        }

        function createColorPalette(colors) {
            // Clear previous palette
            colorPalette.innerHTML = '';

            // Create color boxes
            colors.forEach(color => {
                const colorBox = document.createElement('div');
                colorBox.className = 'color-box';
                colorBox.style.backgroundColor = color;

                const colorCode = document.createElement('div');
                colorCode.className = 'color-code';
                colorCode.textContent = color;

                colorBox.appendChild(colorCode);
                colorPalette.appendChild(colorBox);
            });
        }

        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            loadingSection.style.display = 'none';
        }

        function formatDate(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        }
    </script>
</body>
</html>
    ''')

if __name__ == '__main__':
    print("Setting up the Spotify Album Color Extractor...")
    print("Before running this script, make sure you have:")
    print("1. Created a Spotify Developer App")
    print("2. Set the redirect URI to http://localhost:5000/callback")
    print("3. Created a .env file with your credentials:")
    print("   SPOTIFY_CLIENT_ID=your_client_id")
    print("   SPOTIFY_CLIENT_SECRET=your_client_secret")
    print("   REDIRECT_URI=http://localhost:5000/callback")
    print("\nInstall the required packages with:")
    print("pip install flask flask-cors requests Pillow colorthief python-dotenv")
    print("\nRun the app with:")
    print("python spotify_color_extractor.py")
    print("\nThen open http://localhost:5000 in your browser")

    app.run(debug=True)