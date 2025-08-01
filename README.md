# OneLens

A full-stack application with Python backend and React frontend.

## Project Structure

```
onelens/
├── backend/          # Python FastAPI backend
│   ├── main.py      # Main application entry point
│   └── pyproject.toml # Dependencies managed by uv
├── frontend/         # React frontend with Vite
│   ├── src/         # React source code
│   ├── package.json # Node dependencies
│   └── vite.config.js
└── README.md
```

## Getting Started

### Backend

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Run the FastAPI server:
   ```bash
   uv run python main.py
   ```

   The API will be available at http://localhost:8000

### Frontend

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies (if not already done):
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

   The React app will be available at http://localhost:5173

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check endpoint
