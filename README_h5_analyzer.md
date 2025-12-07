# H5 Image Analyzer GUI

A graphical user interface for analyzing images stored in HDF5 files, with the ability to draw rectangular regions and count pixels.

## Features

- **H5 File Loading**: Automatically detects and loads image datasets from HDF5 files
- **Dual Analysis Modes**: 
  - Single Image Analysis: Analyze individual images with custom regions
  - Dataset Analysis: Define regions on first image, apply to all images in a dataset
- **Image Display**: View images with zoom, pan, and navigation capabilities
- **Region Selection**: Draw rectangular regions by clicking and dragging
- **Pixel Analysis**: Count non-zero pixels and calculate intensity statistics for selected regions
- **Time-Series Plotting**: Plot pixel count vs image number for dataset analysis
- **Export Results**: Save analysis results in JSON, CSV, or text format
- **Multi-Image Support**: Switch between different images and datasets in the same H5 file

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running the Application

```bash
python run_h5_analyzer.py
```

Or directly:
```bash
python h5_image_analyzer.py
```

### Using the GUI

#### Single Image Analysis Mode
1. **Load H5 File**: Click "Load H5 File" to select an HDF5 file containing images
2. **Select Mode**: Choose "Single Image" from the Analysis Mode dropdown
3. **Select Image**: Use the dropdown to choose which image to analyze (📷 prefix indicates single images)
4. **Draw Regions**: Click and drag on the image to draw rectangular regions of interest
5. **Analyze**: Click "Analyze Regions" to calculate pixel counts and statistics
6. **Save Results**: Use "Save Analysis Results" to export your analysis

#### Dataset Analysis Mode (Time-Series)
1. **Load H5 File**: Click "Load H5 File" to select an HDF5 file containing image datasets
2. **Select Mode**: Choose "Dataset Analysis" from the Analysis Mode dropdown
3. **Select Dataset**: Use the dropdown to choose which dataset to analyze (📊 prefix indicates datasets)
4. **Define Regions**: Click "Define Regions on First Image" and draw regions on the first image
5. **Apply Analysis**: Click "Apply Regions to All Images" to analyze all images in the dataset
6. **Plot Results**: Click "Plot Pixel Count vs Image Number" to visualize the time-series data
7. **Save Results**: Use "Save Analysis Results" to export your dataset analysis

### Region Analysis

For each selected region, the tool calculates:
- **Pixel Count**: Number of non-zero pixels in the region
- **Total Pixels**: Total number of pixels in the region
- **Mean Intensity**: Average pixel intensity
- **Max/Min Intensity**: Highest and lowest pixel values

### Supported File Formats

- HDF5 files (.h5, .hdf5)
- Automatically detects 2D and 3D image datasets
- Handles various data types (float, int, etc.)

## Technical Details

### Architecture

- **Main Window**: `H5ImageAnalyzer` - Main application window
- **Image Canvas**: `ImageCanvas` - Custom matplotlib canvas for image display and region selection
- **File Loader**: `H5FileLoader` - Background thread for loading H5 files
- **Region Analysis**: Built-in pixel counting and statistics calculation

### Key Components

- **PyQt5**: GUI framework
- **Matplotlib**: Image display and region drawing
- **H5py**: HDF5 file reading
- **NumPy**: Image data processing

## Integration with ARTIQ

This tool is designed to work with ARTIQ experiment data. It can analyze:
- Camera images from ARTIQ experiments
- Scan data stored in H5 format
- Any image data saved during ARTIQ runs

## Troubleshooting

### Common Issues

1. **No images found**: Ensure your H5 file contains 2D or 3D datasets
2. **Import errors**: Install all required dependencies with `pip install -r requirements.txt`
3. **Memory issues**: Large images may require more RAM; consider resizing images if needed

### Performance Tips

- The tool automatically handles large H5 files by loading images on-demand
- Region analysis is performed in real-time
- Results can be saved to avoid re-analysis

## Example Workflows

### Single Image Analysis
1. Run an ARTIQ experiment that saves camera data to an H5 file
2. Open the H5 Image Analyzer
3. Load the experiment's H5 file
4. Select "Single Image" mode
5. Choose the camera image dataset
6. Draw regions around areas of interest (e.g., atomic clouds, MOT regions)
7. Analyze to get pixel counts and statistics
8. Save results for further analysis or reporting

### Dataset Analysis (Time-Series)
1. Run an ARTIQ experiment that saves a sequence of camera images to an H5 file
2. Open the H5 Image Analyzer
3. Load the experiment's H5 file
4. Select "Dataset Analysis" mode
5. Choose the image dataset (e.g., `detection.images.X`)
6. Define regions on the first image
7. Apply regions to all images in the dataset
8. Plot pixel count vs image number to see temporal evolution
9. Save results in CSV format for further analysis

This tool is particularly useful for:
- **MOT Loading Analysis**: Track atomic cloud growth over time
- **Fluorescence Decay**: Monitor signal intensity changes
- **Scan Analysis**: Analyze data from frequency or parameter scans
- **System Characterization**: Monitor imaging system performance over time
- **Quality Control**: Track experimental stability across multiple shots
