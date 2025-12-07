# ARTIQ Image Analyzer

A specialized GUI tool for analyzing ARTIQ detection images with port-based analysis, marginal distributions, and ratio calculations.

## Features

- **H5 File Loading**: Automatically loads datasets from `datasets/detection.images.X` where X is an integer
- **Image Display**: View images with 90-degree rotation and Blues colormap
- **Port Definition**: Draw rectangular regions (ports) on images by clicking and dragging
- **Marginal Distributions**: Plot X and Y marginal distributions for each port
- **Ratio Calculations**: Define and calculate ratios between port pixel sums
- **Multi-Image Support**: Navigate through image sequences in datasets
- **Tabbed Interface**: Organized analysis with separate tabs for different functions

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running the Application

```bash
python run_artiq_analyzer.py
```

Or directly:
```bash
python artiq_image_analyzer.py
```

### Using the GUI

#### 1. Load H5 File
- Click "Load H5 File" to select an HDF5 file
- The tool automatically finds datasets matching `datasets/detection.images.X` pattern
- Only integer X values are loaded (e.g., `datasets/detection.images.0`, `datasets/detection.images.1`)

#### 2. Select Dataset
- Use the dropdown to choose which dataset to analyze
- Navigate through multiple images using Previous/Next buttons
- Image information is displayed showing current position

#### 3. Define Ports
- Click and drag on the image to draw rectangular regions (ports)
- Each port is automatically numbered and colored
- Ports list shows all defined regions with their coordinates and dimensions
- Use "Clear All Ports" to remove all defined regions

#### 4. Analyze Marginal Distributions
- Click "Plot Marginal Distributions" to see X and Y marginals for each port
- X marginal: sum along Y axis (vertical projection)
- Y marginal: sum along X axis (horizontal projection)
- Each port gets its own subplot

#### 5. Define and Calculate Ratios
- Click "Define Ratio" to create ratio calculations
- Choose numerator port
- Choose denominator (single port or sum of multiple ports)
- Click "Calculate Ratios" to compute values for current image
- Results are displayed in the Ratio Analysis tab

## Interface Layout

### Left Panel (Controls)
- **File Operations**: Load H5 files
- **Dataset Selection**: Choose dataset and navigate images
- **Port Operations**: Manage defined ports
- **Analysis**: Access marginal distributions and ratio calculations

### Right Panel (Analysis)
- **Image Display Tab**: Main image with port overlays
- **Marginal Distributions Tab**: Plots of port marginals
- **Ratio Analysis Tab**: Ratio calculation results

## Technical Details

### Port Analysis
- **Port Definition**: User-drawn rectangular regions
- **Pixel Sum**: Total intensity within each port
- **Marginal Distributions**: Projections along X and Y axes
- **Color Coding**: Each port gets a unique color for easy identification

### Ratio Calculations
- **Numerator**: Single port pixel sum
- **Denominator**: Single port or sum of multiple ports
- **Flexible Definitions**: Mix and match ports for complex ratios
- **Real-time Calculation**: Results update for current image

### Image Processing
- **90-Degree Rotation**: All images rotated clockwise
- **Blues Colormap**: Optimized for scientific imaging
- **Automatic Scaling**: Each image scales to fit display
- **Multi-Image Support**: Navigate through image sequences

## Example Workflows

### Basic Port Analysis
1. Load H5 file with detection images
2. Select dataset (e.g., `datasets/detection.images.0`)
3. Draw ports around regions of interest
4. Plot marginal distributions to analyze spatial profiles
5. Calculate ratios between different ports

### Multi-Image Analysis
1. Load dataset with multiple images
2. Define ports on first image
3. Navigate through images to see how ports perform
4. Calculate ratios for each image
5. Compare results across the image sequence

### Complex Ratio Analysis
1. Define multiple ports (e.g., signal, background, reference)
2. Create ratios like: signal/(signal+background)
3. Define multiple ratio types for comprehensive analysis
4. Calculate all ratios for current image

## File Format Support

- **HDF5 Files**: `.h5` and `.hdf5` extensions
- **Dataset Pattern**: `datasets/detection.images.X` where X is integer
- **Image Types**: 2D single images or 3D image sequences
- **Data Types**: Supports various HDF5 data types

## Troubleshooting

### Common Issues
1. **No datasets found**: Ensure H5 file contains `datasets/detection.images.X` pattern
2. **Import errors**: Install dependencies with `pip install -r requirements.txt`
3. **Memory issues**: Large image sequences may require more RAM

### Performance Tips
- Ports are defined once and applied to all images
- Marginal distributions are calculated on-demand
- Ratio calculations are fast and real-time
- Large datasets are loaded efficiently

This tool is specifically designed for ARTIQ experiment analysis and provides a comprehensive interface for port-based image analysis with advanced ratio calculations and marginal distribution plotting.
