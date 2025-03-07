# Bibliography Organizer

An AI-powered tool that automatically organizes academic PDF files by analyzing their filenames and creating a logical folder structure.

## Overview

This tool helps researchers and academics organize their PDF documents by:
- Extracting metadata (title, author) from filenames using AI
- Creating an intelligent folder structure based on document categories
- Renaming files consistently using author-title format
- Supporting interrupted operations through a resume feature

## Requirements

- Python 3.6+
- OpenRouter API key (get one at https://openrouter.ai)
- Required Python packages:
  - requests
  - PyPDF2
  - pathlib

## Installation

1. Install required packages:
```bash
pip install requests PyPDF2 pathlib
```
2. When prompted:
   - Enter your OpenRouter API key
   - Provide the path to your PDF files
   - Choose whether to resume a previous organization session
## Features
### AI-Powered Metadata Extraction
- Analyzes filenames to extract document titles and authors
- Uses OpenRouter API for intelligent text processing
- Caches results to avoid reprocessing
### Smart Organization
- Creates logical folder hierarchies
- Supports nested folder structures
- Renames files consistently: AuthorName-Title.pdf
### Resume Capability
- Can continue interrupted organization sessions
- Stores organization plans in log file
- Supports manual input of previous organization schemes
### Logging
- Detailed operation logs in bibliography_organizer.log
- Tracks all file operations and errors
- Helps with troubleshooting
## Example
Input folder structure:
```plaintext
Documents/
    paper1.pdf
    paper2.pdf
    book1.pdf
```
Possible output:
```plaintext
Documents/
    Physics/
        Quantum/
            Einstein-QuantumTheory.pdf
    Mathematics/
        Algebra/
            Gauss-LinearAlgebra.pdf
```
## Error Handling
- Validates API key and folder paths
- Handles missing or invalid metadata gracefully
- Provides clear error messages
- Prevents duplicate processing
## Notes
- Requires internet connection for API access
- API key must be obtained from OpenRouter
- Original files are moved, not copied