# CAS Parser API

A FastAPI service for parsing Consolidated Account Statement (CAS) PDFs from CAMS and NSDL.

## Features
- Parse CAS PDFs and extract investment data
- Support for both CAMS and NSDL formats
- Output in JSON or Excel format
- Web interface for easy usage
- API endpoints for integration

## Tech Stack
- Python 3.11
- FastAPI
- pdfplumber
- pandas
- Docker support

## API Endpoints
- `POST /parse/cas`: Upload and parse CAS PDF
- `GET /health`: Health check endpoint
- `GET /`: Web interface

## Environment Variables
- `PORT`: Server port (default: 8080)
- `API_KEY`: API authentication key
- `MAX_FILE_SIZE_MB`: Maximum file size (default: 10)
- `RATE_LIMIT_PER_MINUTE`: Rate limit per IP (default: 60)

## Deployment
Deployed on Render using Python runtime.
