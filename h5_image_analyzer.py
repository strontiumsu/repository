#!/usr/bin/env python3
"""
H5 Image Analyzer GUI
A tool for reading H5 files, displaying images, and analyzing rectangular regions.
"""

import sys
import os
import h5py
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib.patches as patches
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QFileDialog, QLabel, QSpinBox, 
                            QComboBox, QTextEdit, QSplitter, QGroupBox, QGridLayout,
                            QMessageBox, QSlider, QCheckBox, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import json
from datetime import datetime


class ImageCanvas(FigureCanvas):
    """Custom matplotlib canvas for image display and region selection."""
    
    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)
        
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect('equal')
        
        # Image and region data
        self.current_image = None
        self.image_data = None
        self.regions = []  # List of (x, y, width, height) tuples
        self.region_patches = []  # List of Rectangle patches
        
        # Drawing state
        self.drawing = False
        self.start_point = None
        self.current_rectangle = None
        
        # Connect mouse events
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('button_release_event', self.on_release)
        self.mpl_connect('motion_notify_event', self.on_motion)
        
    def load_image(self, image_data, title="Image"):
        """Load and display an image with 90-degree rotation and Blues colormap."""
        # Clear previous image and colorbar
        self.ax.clear()
        
        # Rotate image 90 degrees clockwise
        rotated_image = np.rot90(image_data, k=-1)  # k=-1 rotates 90 degrees clockwise
        
        self.image_data = rotated_image
        self.current_image = self.ax.imshow(rotated_image, cmap='Blues', origin='upper')
        self.ax.set_title(title)
        self.ax.set_xlabel('X (pixels)')
        self.ax.set_ylabel('Y (pixels)')
        
        # Add colorbar
        self.fig.colorbar(self.current_image, ax=self.ax, label='Intensity')
        
        # Reset axis limits to fit the new image
        self.ax.set_xlim(0, rotated_image.shape[1])
        self.ax.set_ylim(0, rotated_image.shape[0])
        
        self.draw()
        
    def on_press(self, event):
        """Handle mouse press event for region drawing."""
        if event.inaxes != self.ax or event.button != 1:
            return
            
        self.drawing = True
        self.start_point = (event.xdata, event.ydata)
        
    def on_motion(self, event):
        """Handle mouse motion during region drawing."""
        if not self.drawing or event.inaxes != self.ax:
            return
            
        if self.current_rectangle:
            self.current_rectangle.remove()
            
        if self.start_point:
            x1, y1 = self.start_point
            x2, y2 = event.xdata, event.ydata
            
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            x = min(x1, x2)
            y = min(y1, y2)
            
            self.current_rectangle = Rectangle((x, y), width, height, 
                                             linewidth=2, edgecolor='red', 
                                             facecolor='none', alpha=0.7)
            self.ax.add_patch(self.current_rectangle)
            self.draw()
            
    def on_release(self, event):
        """Handle mouse release event to finalize region."""
        if not self.drawing or event.inaxes != self.ax:
            return
            
        self.drawing = False
        
        if self.start_point and event.xdata and event.ydata:
            x1, y1 = self.start_point
            x2, y2 = event.xdata, event.ydata
            
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            x = min(x1, x2)
            y = min(y1, y2)
            
            # Add region to list
            region = (int(x), int(y), int(width), int(height))
            self.regions.append(region)
            
            # Create permanent rectangle patch
            rect = Rectangle((x, y), width, height, 
                           linewidth=2, edgecolor='blue', 
                           facecolor='none', alpha=0.7)
            self.ax.add_patch(rect)
            self.region_patches.append(rect)
            
            # Remove temporary rectangle
            if self.current_rectangle:
                self.current_rectangle.remove()
                self.current_rectangle = None
                
            self.draw()
            
            # Notify parent that regions have been added (for button enabling)
            if hasattr(self, 'parent_window'):
                self.parent_window.on_regions_changed()
            
    def clear_regions(self):
        """Clear all selected regions."""
        for patch in self.region_patches:
            patch.remove()
        self.region_patches.clear()
        self.regions.clear()
        self.draw()
        
        # Notify parent that regions have been cleared
        if hasattr(self, 'parent_window'):
            self.parent_window.on_regions_changed()
        
    def get_region_pixel_counts(self):
        """Calculate pixel counts for all regions."""
        if self.image_data is None:
            return []
            
        counts = []
        for x, y, width, height in self.regions:
            # Ensure coordinates are within image bounds
            x = max(0, min(x, self.image_data.shape[1] - 1))
            y = max(0, min(y, self.image_data.shape[0] - 1))
            width = min(width, self.image_data.shape[1] - x)
            height = min(height, self.image_data.shape[0] - y)
            
            # Extract region and count non-zero pixels
            region_data = self.image_data[y:y+height, x:x+width]
            pixel_count = np.count_nonzero(region_data)
            total_pixels = region_data.size
            
            counts.append({
                'region': (x, y, width, height),
                'pixel_count': int(pixel_count),
                'total_pixels': int(total_pixels),
                'mean_intensity': float(np.mean(region_data)),
                'max_intensity': float(np.max(region_data)),
                'min_intensity': float(np.min(region_data))
            })
            
        return counts


class H5FileLoader(QThread):
    """Thread for loading H5 files to prevent GUI freezing."""
    
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        
    def run(self):
        """Load H5 file and extract image data."""
        try:
            self.progress.emit(10)
            
            with h5py.File(self.filename, 'r') as f:
                self.progress.emit(30)
                
                # Find all datasets that look like images
                images = {}
                datasets = {}
                self._find_images(f, images, datasets, "")
                
                self.progress.emit(80)
                
                if not images and not datasets:
                    self.error.emit("No image datasets found in H5 file")
                    return
                    
                self.progress.emit(100)
                self.finished.emit({'images': images, 'datasets': datasets})
                
        except Exception as e:
            self.error.emit(f"Error loading H5 file: {str(e)}")
            
    def _find_images(self, group, images, datasets, prefix):
        """Recursively find image datasets in H5 file, focusing on datasets/detection.images.X where X is integer."""
        for key in group.keys():
            item = group[key]
            full_key = f"{prefix}/{key}" if prefix else key
            
            # Only look for datasets in datasets/detection.images path with integer X
            if (full_key.startswith("datasets/detection.images") or full_key.startswith("/datasets/detection.images")):
                # Check if the path ends with an integer (e.g., datasets/detection.images.0, datasets/detection.images.1, etc.)
                path_parts = full_key.split('.')
                if len(path_parts) >= 2:
                    try:
                        # Check if the last part is an integer
                        int(path_parts[-1])
                        is_valid_dataset = True
                    except ValueError:
                        is_valid_dataset = False
                else:
                    is_valid_dataset = False
                
                if is_valid_dataset and isinstance(item, h5py.Dataset):
                    # Check if dataset looks like an image (2D or 3D with reasonable dimensions)
                    if len(item.shape) >= 2:
                        if len(item.shape) == 2:  # 2D image
                            images[full_key] = item[:]
                        elif len(item.shape) == 3:  # 3D - could be multiple images
                            if item.shape[0] <= 100:  # Reasonable number of frames
                                # Store as dataset for time-series analysis
                                datasets[full_key] = item[:]
                            else:
                                # Take first frame for single image
                                images[full_key] = item[0]
            elif isinstance(item, h5py.Group):
                # Continue searching in groups
                self._find_images(item, images, datasets, full_key)


class H5ImageAnalyzer(QMainWindow):
    """Main application window for H5 image analysis."""
    
    def __init__(self):
        super().__init__()
        self.images = {}
        self.datasets = {}  # Store datasets separately from single images
        self.current_image_key = None
        self.current_dataset_key = None
        self.defined_regions = []  # Regions defined on first image
        self.analysis_mode = "single"  # "single" or "dataset"
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("H5 Image Analyzer")
        self.setGeometry(100, 100, 1400, 900)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - controls
        left_panel = self.create_control_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - image display
        right_panel = self.create_image_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([300, 1100])
        
    def create_control_panel(self):
        """Create the left control panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # File operations
        file_group = QGroupBox("File Operations")
        file_layout = QVBoxLayout(file_group)
        
        self.load_btn = QPushButton("Load H5 File")
        self.load_btn.clicked.connect(self.load_h5_file)
        file_layout.addWidget(self.load_btn)
        
        self.save_results_btn = QPushButton("Save Analysis Results")
        self.save_results_btn.clicked.connect(self.save_results)
        self.save_results_btn.setEnabled(False)
        file_layout.addWidget(self.save_results_btn)
        
        layout.addWidget(file_group)
        
        # Analysis mode selection
        mode_group = QGroupBox("Analysis Mode")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single Image", "Dataset Analysis"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(QLabel("Analysis Mode:"))
        mode_layout.addWidget(self.mode_combo)
        
        layout.addWidget(mode_group)
        
        # Image/Dataset selection
        selection_group = QGroupBox("Data Selection")
        selection_layout = QVBoxLayout(selection_group)
        
        self.image_combo = QComboBox()
        self.image_combo.currentTextChanged.connect(self.on_image_changed)
        selection_layout.addWidget(QLabel("Select Image/Dataset:"))
        selection_layout.addWidget(self.image_combo)
        
        # Dataset-specific controls
        self.dataset_controls = QWidget()
        dataset_layout = QVBoxLayout(self.dataset_controls)
        
        self.define_regions_btn = QPushButton("Define Regions on First Image")
        self.define_regions_btn.clicked.connect(self.define_regions_mode)
        self.define_regions_btn.setEnabled(False)
        dataset_layout.addWidget(self.define_regions_btn)
        
        self.apply_regions_btn = QPushButton("Apply Regions to All Images")
        self.apply_regions_btn.clicked.connect(self.apply_regions_to_dataset)
        self.apply_regions_btn.setEnabled(False)
        dataset_layout.addWidget(self.apply_regions_btn)
        
        self.plot_results_btn = QPushButton("Plot Pixel Count vs Image Number")
        self.plot_results_btn.clicked.connect(self.plot_dataset_analysis)
        self.plot_results_btn.setEnabled(False)
        dataset_layout.addWidget(self.plot_results_btn)
        
        selection_layout.addWidget(self.dataset_controls)
        layout.addWidget(selection_group)
        
        # Region operations
        region_group = QGroupBox("Region Operations")
        region_layout = QVBoxLayout(region_group)
        
        self.clear_regions_btn = QPushButton("Clear All Regions")
        self.clear_regions_btn.clicked.connect(self.clear_regions)
        self.clear_regions_btn.setEnabled(False)
        region_layout.addWidget(self.clear_regions_btn)
        
        self.analyze_btn = QPushButton("Analyze Regions")
        self.analyze_btn.clicked.connect(self.analyze_regions)
        self.analyze_btn.setEnabled(False)
        region_layout.addWidget(self.analyze_btn)
        
        layout.addWidget(region_group)
        
        # Analysis results
        results_group = QGroupBox("Analysis Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_text = QTextEdit()
        self.results_text.setMaximumHeight(200)
        self.results_text.setReadOnly(True)
        results_layout.addWidget(self.results_text)
        
        layout.addWidget(results_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Stretch to push everything to top
        layout.addStretch()
        
        return panel
        
    def create_image_panel(self):
        """Create the right image display panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Image canvas
        self.canvas = ImageCanvas(self, width=10, height=8)
        self.canvas.parent_window = self  # Set reference for callbacks
        layout.addWidget(self.canvas)
        
        # Instructions
        instructions = QLabel("Instructions: Click and drag to draw rectangular regions. Right-click to clear regions.")
        instructions.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(instructions)
        
        return panel
        
    def load_h5_file(self):
        """Load an H5 file and extract images."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open H5 File", "", "HDF5 Files (*.h5 *.hdf5);;All Files (*)"
        )
        
        if filename:
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # Disable buttons during loading
            self.load_btn.setEnabled(False)
            
            # Start loading thread
            self.loader = H5FileLoader(filename)
            self.loader.progress.connect(self.progress_bar.setValue)
            self.loader.finished.connect(self.on_h5_loaded)
            self.loader.error.connect(self.on_load_error)
            self.loader.start()
            
    def on_h5_loaded(self, data):
        """Handle successful H5 file loading."""
        self.images = data['images']
        self.datasets = data['datasets']
        self.progress_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        
        # Debug: Print what was loaded
        print(f"Loaded {len(self.images)} single images: {list(self.images.keys())}")
        print(f"Loaded {len(self.datasets)} datasets: {list(self.datasets.keys())}")
        
        # Update image combo box with both images and datasets
        self.image_combo.clear()
        all_items = []
        if self.images:
            all_items.extend([f"📷 {key}" for key in self.images.keys()])
        if self.datasets:
            all_items.extend([f"📊 {key}" for key in self.datasets.keys()])
        self.image_combo.addItems(all_items)
        
        # Enable buttons
        self.clear_regions_btn.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.save_results_btn.setEnabled(True)
        
        # Load first item
        if all_items:
            self.on_image_changed(all_items[0])
            
    def on_load_error(self, error_msg):
        """Handle H5 file loading error."""
        self.progress_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", error_msg)
        
    def on_mode_changed(self, mode_text):
        """Handle analysis mode change."""
        self.analysis_mode = "dataset" if mode_text == "Dataset Analysis" else "single"
        print(f"Mode changed to: {self.analysis_mode}")
        self.update_ui_for_mode()
        
    def update_ui_for_mode(self):
        """Update UI elements based on current analysis mode."""
        is_dataset_mode = self.analysis_mode == "dataset"
        self.dataset_controls.setVisible(is_dataset_mode)
        
        print(f"update_ui_for_mode: is_dataset_mode={is_dataset_mode}, current_dataset_key={self.current_dataset_key}")
        
        if is_dataset_mode and self.current_dataset_key:
            self.define_regions_btn.setEnabled(True)
            # Enable apply regions button if we already have regions
            self.apply_regions_btn.setEnabled(len(self.canvas.regions) > 0)
            # Enable plot button if we have analysis results
            self.plot_results_btn.setEnabled(hasattr(self, 'dataset_results') and self.dataset_results)
            print(f"Dataset mode: define_btn={self.define_regions_btn.isEnabled()}, apply_btn={self.apply_regions_btn.isEnabled()}, plot_btn={self.plot_results_btn.isEnabled()}")
        else:
            self.define_regions_btn.setEnabled(False)
            self.apply_regions_btn.setEnabled(False)
            self.plot_results_btn.setEnabled(False)
            print(f"Non-dataset mode: all buttons disabled")
            
    def on_image_changed(self, item_text):
        """Handle image/dataset selection change."""
        print(f"Image changed to: {item_text}")
        print(f"Current analysis mode: {self.analysis_mode}")
        
        # Extract the actual key from the display text
        if item_text.startswith("📷 "):
            image_key = item_text[2:]  # Remove emoji prefix
            if image_key in self.images:
                self.current_image_key = image_key
                self.current_dataset_key = None
                self.display_image(image_key)
        elif item_text.startswith("📊 "):
            dataset_key = item_text[2:]  # Remove emoji prefix
            if dataset_key in self.datasets:
                self.current_dataset_key = dataset_key
                self.current_image_key = None
                self.display_dataset_first_image(dataset_key)
                print(f"Selected dataset: {dataset_key}")
        
        self.update_ui_for_mode()
        print(f"Define regions button enabled: {self.define_regions_btn.isEnabled()}")
        print(f"Apply regions button enabled: {self.apply_regions_btn.isEnabled()}")
        print(f"Plot results button enabled: {self.plot_results_btn.isEnabled()}")
        
    def on_regions_changed(self):
        """Handle when regions are added or removed."""
        if self.analysis_mode == "dataset" and self.current_dataset_key:
            # Enable apply regions button if we have regions
            self.apply_regions_btn.setEnabled(len(self.canvas.regions) > 0)
            # Disable plot button until analysis is complete
            self.plot_results_btn.setEnabled(False)
            
    def display_image(self, image_key):
        """Display the selected image."""
        if image_key in self.images:
            image_data = self.images[image_key]
            self.canvas.load_image(image_data, f"Image: {image_key}")
            
    def display_dataset_first_image(self, dataset_key):
        """Display the first image from a dataset."""
        if dataset_key in self.datasets:
            dataset_data = self.datasets[dataset_key]
            first_image = dataset_data[0]  # First frame
            self.canvas.load_image(first_image, f"Dataset: {dataset_key} (Image 0/{len(dataset_data)-1})")
            
    def define_regions_mode(self):
        """Enter region definition mode for dataset analysis."""
        if self.current_dataset_key and self.analysis_mode == "dataset":
            self.define_regions_btn.setText("Regions Defined - Click to Redefine")
            self.define_regions_btn.setStyleSheet("background-color: lightgreen;")
            # Enable the apply regions button
            self.apply_regions_btn.setEnabled(True)
            QMessageBox.information(self, "Region Definition", 
                                  "Draw rectangular regions on the first image. These regions will be applied to all images in the dataset.")
            
    def apply_regions_to_dataset(self):
        """Apply defined regions to all images in the dataset."""
        if not self.current_dataset_key or not self.canvas.regions:
            QMessageBox.warning(self, "No Regions", "Please define regions first.")
            return
            
        if self.analysis_mode != "dataset":
            QMessageBox.warning(self, "Wrong Mode", "Please switch to Dataset Analysis mode.")
            return
            
        # Store the defined regions
        self.defined_regions = self.canvas.regions.copy()
        
        # Analyze all images in the dataset
        dataset_data = self.datasets[self.current_dataset_key]
        results = []
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(dataset_data))
        
        for i, image in enumerate(dataset_data):
            self.progress_bar.setValue(i)
            QApplication.processEvents()  # Keep UI responsive
            
            # Rotate the image 90 degrees clockwise to match display
            rotated_image = np.rot90(image, k=-1)
            
            # Calculate pixel counts for each region
            image_results = {'image_number': i}
            region_counts = []
            
            for j, (x, y, width, height) in enumerate(self.defined_regions):
                # Ensure coordinates are within image bounds (use rotated image dimensions)
                x = max(0, min(x, rotated_image.shape[1] - 1))
                y = max(0, min(y, rotated_image.shape[0] - 1))
                width = min(width, rotated_image.shape[1] - x)
                height = min(height, rotated_image.shape[0] - y)
                
                # Extract region and count pixels
                region_data = rotated_image[y:y+height, x:x+width]
                pixel_count = np.count_nonzero(region_data)
                total_pixels = region_data.size
                
                region_counts.append({
                    'region_id': j + 1,
                    'pixel_count': int(pixel_count),
                    'total_pixels': int(total_pixels),
                    'mean_intensity': float(np.mean(region_data)),
                    'max_intensity': float(np.max(region_data)),
                    'min_intensity': float(np.min(region_data))
                })
                
            image_results['regions'] = region_counts
            image_results['total_pixels'] = sum(r['pixel_count'] for r in region_counts)
            results.append(image_results)
            
        self.progress_bar.setVisible(False)
        
        # Store results for plotting
        self.dataset_results = results
        self.apply_regions_btn.setEnabled(False)
        self.plot_results_btn.setEnabled(True)
        
        # Display summary
        total_images = len(results)
        total_regions = len(self.defined_regions)
        self.results_text.setText(f"Dataset Analysis Complete!\n\n"
                                f"Analyzed {total_images} images with {total_regions} regions each.\n"
                                f"Click 'Plot Pixel Count vs Image Number' to visualize results.")
        
    def plot_dataset_analysis(self):
        """Plot pixel count vs image number for all regions."""
        if not hasattr(self, 'dataset_results') or not self.dataset_results:
            QMessageBox.warning(self, "No Data", "Please run dataset analysis first.")
            return
            
        # Create a new window for plotting
        plot_window = QMainWindow()
        plot_window.setWindowTitle(f"Dataset Analysis: {self.current_dataset_key}")
        plot_window.setGeometry(200, 200, 1000, 600)
        
        # Create matplotlib figure
        fig = Figure(figsize=(10, 6))
        canvas = FigureCanvas(fig)
        plot_window.setCentralWidget(canvas)
        
        ax = fig.add_subplot(111)
        
        # Extract data for plotting
        image_numbers = [r['image_number'] for r in self.dataset_results]
        total_pixels = [r['total_pixels'] for r in self.dataset_results]
        
        
        # Plot total pixel count
        ax.plot(image_numbers, total_pixels, 'b-o', linewidth=2, markersize=4, label='Total Pixels')
        
        # Plot individual regions if there are multiple
        if len(self.defined_regions) > 1:
            colors = plt.cm.tab10(np.linspace(0, 1, len(self.defined_regions)))
            for i, region_id in enumerate(range(1, len(self.defined_regions) + 1)):
                region_pixels = [r['regions'][i]['pixel_count'] for r in self.dataset_results]
                ax.plot(image_numbers, region_pixels, '--o', color=colors[i], 
                       linewidth=1, markersize=3, label=f'Region {region_id}')
        
        ax.set_xlabel('Image Number')
        ax.set_ylabel('Pixel Count')
        ax.set_title(f'Pixel Count vs Image Number\nDataset: {self.current_dataset_key}')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Add some statistics
        if total_pixels:  # Check if we have data
            mean_pixels = np.mean(total_pixels)
            std_pixels = np.std(total_pixels)
            ax.text(0.02, 0.98, f'Mean: {mean_pixels:.1f} ± {std_pixels:.1f}', 
                    transform=ax.transAxes, verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        fig.tight_layout()
        canvas.draw()
        
        plot_window.show()
            
    def clear_regions(self):
        """Clear all selected regions."""
        self.canvas.clear_regions()
        self.results_text.clear()
        # Update button states
        self.on_regions_changed()
        
    def analyze_regions(self):
        """Analyze all selected regions and display results."""
        if not self.canvas.regions:
            QMessageBox.information(self, "No Regions", "Please draw some regions first.")
            return
            
        counts = self.canvas.get_region_pixel_counts()
        
        # Display results
        results = f"Analysis Results for {self.current_image_key}:\n"
        results += "=" * 50 + "\n\n"
        
        total_pixels = 0
        for i, count_data in enumerate(counts):
            region = count_data['region']
            pixel_count = count_data['pixel_count']
            total_pixels += pixel_count
            
            results += f"Region {i+1}:\n"
            results += f"  Position: ({region[0]}, {region[1]})\n"
            results += f"  Size: {region[2]} x {region[3]} pixels\n"
            results += f"  Non-zero pixels: {pixel_count}\n"
            results += f"  Total pixels: {count_data['total_pixels']}\n"
            results += f"  Mean intensity: {count_data['mean_intensity']:.2f}\n"
            results += f"  Max intensity: {count_data['max_intensity']:.2f}\n"
            results += f"  Min intensity: {count_data['min_intensity']:.2f}\n\n"
            
        results += f"Total non-zero pixels across all regions: {total_pixels}\n"
        results += f"Number of regions: {len(counts)}\n"
        
        self.results_text.setText(results)
        
    def save_results(self):
        """Save analysis results to a file."""
        if self.analysis_mode == "dataset" and hasattr(self, 'dataset_results'):
            self.save_dataset_results()
        elif self.canvas.regions:
            self.save_single_image_results()
        else:
            QMessageBox.information(self, "No Data", "No regions to save.")
            
    def save_single_image_results(self):
        """Save single image analysis results."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Results", "", "JSON Files (*.json);;Text Files (*.txt);;All Files (*)"
        )
        
        if filename:
            try:
                counts = self.canvas.get_region_pixel_counts()
                
                # Prepare data for saving
                save_data = {
                    'timestamp': datetime.now().isoformat(),
                    'analysis_mode': 'single_image',
                    'image_file': self.current_image_key,
                    'image_shape': self.canvas.image_data.shape if self.canvas.image_data is not None else None,
                    'regions': []
                }
                
                for i, count_data in enumerate(counts):
                    region_data = {
                        'region_id': i + 1,
                        'position': count_data['region'][:2],
                        'size': count_data['region'][2:],
                        'pixel_count': count_data['pixel_count'],
                        'total_pixels': count_data['total_pixels'],
                        'mean_intensity': count_data['mean_intensity'],
                        'max_intensity': count_data['max_intensity'],
                        'min_intensity': count_data['min_intensity']
                    }
                    save_data['regions'].append(region_data)
                
                # Save based on file extension
                if filename.endswith('.json'):
                    with open(filename, 'w') as f:
                        json.dump(save_data, f, indent=2)
                else:
                    with open(filename, 'w') as f:
                        f.write(self.results_text.toPlainText())
                        
                QMessageBox.information(self, "Success", f"Results saved to {filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save results: {str(e)}")
                
    def save_dataset_results(self):
        """Save dataset analysis results."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Dataset Results", "", "JSON Files (*.json);;CSV Files (*.csv);;All Files (*)"
        )
        
        if filename:
            try:
                # Prepare data for saving
                save_data = {
                    'timestamp': datetime.now().isoformat(),
                    'analysis_mode': 'dataset',
                    'dataset_file': self.current_dataset_key,
                    'dataset_shape': self.datasets[self.current_dataset_key].shape,
                    'defined_regions': [{'region_id': i+1, 'position': r[:2], 'size': r[2:]} 
                                      for i, r in enumerate(self.defined_regions)],
                    'results': self.dataset_results
                }
                
                if filename.endswith('.json'):
                    with open(filename, 'w') as f:
                        json.dump(save_data, f, indent=2)
                elif filename.endswith('.csv'):
                    # Create CSV with pixel counts for each region
                    import pandas as pd
                    
                    # Flatten data for CSV
                    csv_data = []
                    for result in self.dataset_results:
                        row = {'image_number': result['image_number'], 'total_pixels': result['total_pixels']}
                        for region in result['regions']:
                            row[f'region_{region["region_id"]}_pixels'] = region['pixel_count']
                            row[f'region_{region["region_id"]}_mean_intensity'] = region['mean_intensity']
                        csv_data.append(row)
                    
                    df = pd.DataFrame(csv_data)
                    df.to_csv(filename, index=False)
                else:
                    # Text format
                    with open(filename, 'w') as f:
                        f.write(f"Dataset Analysis Results\n")
                        f.write(f"Dataset: {self.current_dataset_key}\n")
                        f.write(f"Total Images: {len(self.dataset_results)}\n")
                        f.write(f"Regions: {len(self.defined_regions)}\n\n")
                        
                        for result in self.dataset_results:
                            f.write(f"Image {result['image_number']}: {result['total_pixels']} total pixels\n")
                            for region in result['regions']:
                                f.write(f"  Region {region['region_id']}: {region['pixel_count']} pixels, "
                                       f"mean intensity: {region['mean_intensity']:.2f}\n")
                        
                QMessageBox.information(self, "Success", f"Dataset results saved to {filename}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save results: {str(e)}")


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = H5ImageAnalyzer()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
