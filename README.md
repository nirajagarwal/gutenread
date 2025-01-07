# GutenRead

A web application for searching and discovering books across multiple open-access platforms including OpenLibrary and Project Gutenberg. Features a clean, responsive interface and real-time search capabilities.

## Features

- Search across multiple book platforms simultaneously
- View trending books from different sources
- Responsive design with Bootstrap
- Book details including covers, descriptions, and download links
- Real-time search results

## Tech Stack

- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **Backend**: Python with Quart framework
- **Server**: Uvicorn
- **APIs**: 
  - OpenLibrary
  - Project Gutenberg
  - Directory of Open Access Books (DOAB)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/nirajagarwal/gutenread.git
   cd gutenread
   ```

2. **Set up a virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   ```bash
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/macOS
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

1. **Start the server**:
   ```bash
   uvicorn app:app --reload
   ```

2. **Access the application**:
   Open your browser and navigate to `http://127.0.0.1:8000`

## Screenshots

[Add screenshots of your application here]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- OpenLibrary API
- Project Gutenberg and GutenDex API
- Directory of Open Access Books (DOAB)
