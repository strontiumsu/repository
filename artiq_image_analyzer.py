#!/usr/bin/env python3
"""
ARTIQ Image Analyzer GUI
A specialized tool for analyzing ARTIQ detection images with port-based analysis.
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
from matplotlib import colorbar
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QPushButton, QFileDialog, QLabel, QSpinBox, 
                            QComboBox, QTextEdit, QSplitter, QGroupBox, QGridLayout,
                            QMessageBox, QSlider, QCheckBox, QProgressBar, QLineEdit,
                            QListWidget, QListWidgetItem, QTabWidget)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import json
from datetime import datetime


class ImageCanvas(FigureCanvas):
    """Custom matplotlib canvas for image display and port selection."""
    
    def __init__(self, parent=None, width=10, height=8, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)
        
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect('equal')
        
        # Image and port data
        self.current_image = None
        self.image_data = None
        self.ports = []  # List of port dictionaries
        self.port_patches = []  # List of Rectangle patches
        self.current_colorbar = None  # Reference to current colorbar
        
        # Drawing state
        self.drawing = False
        self.start_point = None
        self.current_rectangle = None
        self.port_counter = 0
        
        # Connect mouse events
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('button_release_event', self.on_release)
        self.mpl_connect('motion_notify_event', self.on_motion)
        self.mpl_connect('button_press_event', self.on_right_click)
        
    def load_image(self, image_data, title="Image"):
        """Load and display an image with 90-degree rotation and Blues colormap."""
        # Clear previous image, colorbar, and all text
        self.ax.clear()
        
        # Remove previous colorbar if it exists
        if self.current_colorbar is not None:
            try:
                self.current_colorbar.remove()
            except (AttributeError, NotImplementedError):
                # Colorbar may already be removed or can't be removed
                pass
            finally:
                self.current_colorbar = None
        
        # Rotate image 90 degrees clockwise
        rotated_image = np.rot90(image_data, k=-1)  # k=-1 rotates 90 degrees clockwise
        
        self.image_data = rotated_image
        self.current_image = self.ax.imshow(rotated_image, cmap='Blues', origin='upper')
        self.ax.set_title(title)
        self.ax.set_xlabel('X (pixels)')
        self.ax.set_ylabel('Y (pixels)')
        
        # Add colorbar and store reference
        self.current_colorbar = self.fig.colorbar(self.current_image, ax=self.ax, label='Intensity')
        
        # Reset axis limits to fit the new image
        self.ax.set_xlim(0, rotated_image.shape[1])
        self.ax.set_ylim(0, rotated_image.shape[0])
        
        # Redraw existing ports
        self.redraw_ports()
        
        self.draw()
        
    def redraw_ports(self):
        """Redraw all existing ports on the current image."""
        for port in self.ports:
            x, y, width, height = port['bounds']
            color = port['color']
            rect = Rectangle((x, y), width, height, 
                           linewidth=2, edgecolor=color, 
                           facecolor='none', alpha=0.7)
            self.ax.add_patch(rect)
            # Add port label above the port
            self.ax.text(x + width/2, y + height + 5, f"P{port['id']}", 
                        ha='center', va='bottom', color=color, fontweight='bold')
        
    def on_press(self, event):
        """Handle mouse press event for port drawing."""
        if event.inaxes != self.ax or event.button != 1:
            return
            
        self.drawing = True
        self.start_point = (event.xdata, event.ydata)
        
    def on_right_click(self, event):
        """Handle right-click event to clear ports."""
        if event.inaxes != self.ax or event.button != 3:
            return
            
        # Check if click is inside any port
        if event.xdata is not None and event.ydata is not None:
            for i, port in enumerate(self.ports):
                x, y, width, height = port['bounds']
                if (x <= event.xdata <= x + width and 
                    y <= event.ydata <= y + height):
                    # Remove this port
                    self.remove_port(i)
                    break
                    
    def remove_port(self, port_index):
        """Remove a specific port by index."""
        if 0 <= port_index < len(self.ports):
            # Remove the patch
            if port_index < len(self.port_patches):
                try:
                    self.port_patches[port_index].remove()
                except (AttributeError, NotImplementedError):
                    # Patch may already be removed or can't be removed
                    pass
                del self.port_patches[port_index]
            
            # Remove the port
            del self.ports[port_index]
            
            # Redraw
            self.draw()
            
            # Notify parent that ports have been changed
            if hasattr(self, 'parent_window'):
                self.parent_window.on_ports_changed()
        
    def on_motion(self, event):
        """Handle mouse motion during port drawing."""
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
        """Handle mouse release event to finalize port."""
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
            
            # Create new port
            self.port_counter += 1
            port = {
                'id': self.port_counter,
                'bounds': (int(x), int(y), int(width), int(height)),
                'color': plt.cm.tab10(self.port_counter % 10)
            }
            self.ports.append(port)
            
            # Create permanent rectangle patch
            rect = Rectangle((x, y), width, height, 
                           linewidth=2, edgecolor=port['color'], 
                           facecolor='none', alpha=0.7)
            self.ax.add_patch(rect)
            self.port_patches.append(rect)
            
            # Add port label above the port
            self.ax.text(x + width/2, y + height + 5, f"P{port['id']}", 
                        ha='center', va='bottom', color=port['color'], fontweight='bold')
            
            # Remove temporary rectangle
            if self.current_rectangle:
                self.current_rectangle.remove()
                self.current_rectangle = None
                
            self.draw()
            
            # Notify parent that ports have been added
            if hasattr(self, 'parent_window'):
                self.parent_window.on_ports_changed()
                
    def clear_ports(self):
        """Clear all defined ports."""
        # Clear all patches
        for patch in self.port_patches:
            try:
                patch.remove()
            except (AttributeError, NotImplementedError):
                # Patch may already be removed or can't be removed
                pass
        self.port_patches.clear()
        
        # Clear only port labels (texts that start with 'P' followed by a number)
        texts_to_remove = []
        for text in self.ax.texts:
            text_content = text.get_text()
            if text_content.startswith('P') and len(text_content) > 1 and text_content[1:].isdigit():
                texts_to_remove.append(text)
        
        for text in texts_to_remove:
            text.remove()
        
        self.ports.clear()
        self.port_counter = 0
        self.draw()
        
        # Notify parent that ports have been cleared
        if hasattr(self, 'parent_window'):
            self.parent_window.on_ports_changed()
            
    def get_port_data(self, port_id):
        """Get pixel data for a specific port."""
        if self.image_data is None:
            return None
            
        for port in self.ports:
            if port['id'] == port_id:
                x, y, width, height = port['bounds']
                # Ensure coordinates are within image bounds
                x = max(0, min(x, self.image_data.shape[1] - 1))
                y = max(0, min(y, self.image_data.shape[0] - 1))
                width = min(width, self.image_data.shape[1] - x)
                height = min(height, self.image_data.shape[0] - y)
                
                return self.image_data[y:y+height, x:x+width]
        return None
        
    def get_port_pixel_sum(self, port_id):
        """Get total pixel sum for a specific port."""
        port_data = self.get_port_data(port_id)
        if port_data is not None:
            pixel_sum = np.sum(port_data)
            print(f"Port {port_id}: shape={port_data.shape}, sum={pixel_sum}")
            return pixel_sum
        print(f"Port {port_id}: No data found")
        return 0


class H5FileLoader(QThread):
    """Thread for loading H5 files to prevent GUI freezing."""
    
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, filename):
        super().__init__()
        self.filename = filename
        
    def run(self):
        """Load H5 file and extract image datasets."""
        try:
            self.progress.emit(10)
            
            with h5py.File(self.filename, 'r') as f:
                self.progress.emit(30)
                
                # Find all datasets matching datasets/detection.images.X where X is integer
                datasets = {}
                self._find_datasets(f, datasets, "")
                
                self.progress.emit(80)
                
                if not datasets:
                    self.error.emit("No valid detection image datasets found in H5 file")
                    return
                    
                self.progress.emit(100)
                self.finished.emit(datasets)
                
        except Exception as e:
            self.error.emit(f"Error loading H5 file: {str(e)}")
            
    def _find_datasets(self, group, datasets, prefix):
        """Recursively find detection image datasets in H5 file."""
        try:
            for key in group.keys():
                try:
                    item = group[key]
                    full_key = f"{prefix}/{key}" if prefix else key
                    
                    # Look for datasets in datasets/detection.images path with integer X
                    if (full_key.startswith("datasets/detection.images") or 
                        full_key.startswith("/datasets/detection.images")):
                        
                        # Check if the path ends with an integer
                        path_parts = full_key.split('.')
                        if len(path_parts) >= 2:
                            try:
                                int(path_parts[-1])  # Check if last part is integer
                                is_valid_dataset = True
                            except ValueError:
                                is_valid_dataset = False
                        else:
                            is_valid_dataset = False
                        
                        if is_valid_dataset and isinstance(item, h5py.Dataset):
                            # Check if dataset looks like images (2D or 3D)
                            if len(item.shape) >= 2:
                                try:
                                    if len(item.shape) == 2:  # 2D image
                                        datasets[full_key] = item[:]
                                    elif len(item.shape) == 3:  # 3D - multiple images
                                        datasets[full_key] = item[:]
                                except Exception as e:
                                    print(f"Warning: Could not load dataset {full_key}: {e}")
                                    continue
                                    
                    elif isinstance(item, h5py.Group):
                        # Continue searching in groups
                        self._find_datasets(item, datasets, full_key)
                except Exception as e:
                    print(f"Warning: Error processing key {key}: {e}")
                    continue
        except Exception as e:
            print(f"Warning: Error in _find_datasets: {e}")


class ARTIQImageAnalyzer(QMainWindow):
    """Main application window for ARTIQ image analysis."""
    
    def __init__(self):
        super().__init__()
        self.datasets = {}
        self.current_dataset_key = None
        self.current_image_index = 0
        self.ratios = []  # Store defined ratios
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("ARTIQ Image Analyzer")
        self.setGeometry(100, 100, 1600, 1000)
        
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
        
        # Right panel - image display and analysis
        right_panel = self.create_analysis_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([400, 1200])
        
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
        
        layout.addWidget(file_group)
        
        # Dataset selection
        dataset_group = QGroupBox("Dataset Selection")
        dataset_layout = QVBoxLayout(dataset_group)
        
        self.dataset_combo = QComboBox()
        self.dataset_combo.currentTextChanged.connect(self.on_dataset_changed)
        dataset_layout.addWidget(QLabel("Select Dataset:"))
        dataset_layout.addWidget(self.dataset_combo)
        
        # Image navigation
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.previous_image)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_image)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)
        
        dataset_layout.addLayout(nav_layout)
        
        self.image_info_label = QLabel("No image loaded")
        dataset_layout.addWidget(self.image_info_label)
        
        layout.addWidget(dataset_group)
        
        # Port operations
        port_group = QGroupBox("Port Operations")
        port_layout = QVBoxLayout(port_group)
        
        self.clear_ports_btn = QPushButton("Clear All Ports")
        self.clear_ports_btn.clicked.connect(self.clear_ports)
        self.clear_ports_btn.setEnabled(False)
        port_layout.addWidget(self.clear_ports_btn)
        
        self.refresh_ports_btn = QPushButton("Refresh Port Counts")
        self.refresh_ports_btn.clicked.connect(self.update_ports_list)
        self.refresh_ports_btn.setEnabled(False)
        port_layout.addWidget(self.refresh_ports_btn)
        
        self.ports_list = QListWidget()
        self.ports_list.setMaximumHeight(150)
        port_layout.addWidget(QLabel("Defined Ports:"))
        port_layout.addWidget(self.ports_list)
        
        layout.addWidget(port_group)
        
        # Analysis operations
        analysis_group = QGroupBox("Analysis")
        analysis_layout = QVBoxLayout(analysis_group)
        
        self.marginal_btn = QPushButton("Plot Marginal Distributions")
        self.marginal_btn.clicked.connect(self.plot_marginal_distributions)
        self.marginal_btn.setEnabled(False)
        analysis_layout.addWidget(self.marginal_btn)
        
        self.ratio_btn = QPushButton("Define Ratio")
        self.ratio_btn.clicked.connect(self.define_ratio)
        self.ratio_btn.setEnabled(False)
        analysis_layout.addWidget(self.ratio_btn)
        
        self.calculate_ratio_btn = QPushButton("Calculate Ratios")
        self.calculate_ratio_btn.clicked.connect(self.calculate_ratios)
        self.calculate_ratio_btn.setEnabled(False)
        analysis_layout.addWidget(self.calculate_ratio_btn)
        
        self.apply_to_all_btn = QPushButton("Apply to All Images")
        self.apply_to_all_btn.clicked.connect(self.apply_ratios_to_all)
        self.apply_to_all_btn.setEnabled(False)
        analysis_layout.addWidget(self.apply_to_all_btn)
        
        layout.addWidget(analysis_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Stretch to push everything to top
        layout.addStretch()
        
        return panel
        
    def create_analysis_panel(self):
        """Create the right analysis panel with tabs."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # Image display tab
        image_tab = QWidget()
        image_layout = QVBoxLayout(image_tab)
        
        self.canvas = ImageCanvas(self, width=12, height=10)
        self.canvas.parent_window = self
        image_layout.addWidget(self.canvas)
        
        instructions = QLabel("Instructions: Left-click and drag to draw ports. Right-click inside a port to delete it.")
        instructions.setStyleSheet("color: gray; font-style: italic;")
        image_layout.addWidget(instructions)
        
        tab_widget.addTab(image_tab, "Image Display")
        
        # Marginal distributions tab
        marginal_tab = QWidget()
        marginal_layout = QVBoxLayout(marginal_tab)
        
        self.marginal_canvas = FigureCanvas(Figure(figsize=(10, 8)))
        marginal_layout.addWidget(self.marginal_canvas)
        
        tab_widget.addTab(marginal_tab, "Marginal Distributions")
        
        # Ratio analysis tab
        ratio_tab = QWidget()
        ratio_layout = QVBoxLayout(ratio_tab)
        
        self.ratio_text = QTextEdit()
        self.ratio_text.setReadOnly(True)
        ratio_layout.addWidget(QLabel("Ratio Analysis Results:"))
        ratio_layout.addWidget(self.ratio_text)
        
        tab_widget.addTab(ratio_tab, "Ratio Analysis")
        
        # Results tab for plots
        results_tab = QWidget()
        results_layout = QVBoxLayout(results_tab)
        
        # X-axis selection controls
        xaxis_group = QGroupBox("X-Axis Options")
        xaxis_layout = QVBoxLayout(xaxis_group)
        
        self.xaxis_combo = QComboBox()
        self.xaxis_combo.addItems(["Index", "Scan Parameter", "User Defined"])
        self.xaxis_combo.currentTextChanged.connect(self.on_xaxis_changed)
        xaxis_layout.addWidget(QLabel("X-Axis Type:"))
        xaxis_layout.addWidget(self.xaxis_combo)
        
        # User defined range controls
        self.user_range_widget = QWidget()
        user_range_layout = QHBoxLayout(self.user_range_widget)
        user_range_layout.addWidget(QLabel("Min:"))
        self.xmin_edit = QLineEdit("0")
        self.xmin_edit.setMaximumWidth(80)
        self.xmin_edit.returnPressed.connect(self.on_user_range_changed)
        self.xmin_edit.textChanged.connect(self.on_user_range_changed)
        user_range_layout.addWidget(self.xmin_edit)
        user_range_layout.addWidget(QLabel("Max:"))
        self.xmax_edit = QLineEdit("100")
        self.xmax_edit.setMaximumWidth(80)
        self.xmax_edit.returnPressed.connect(self.on_user_range_changed)
        self.xmax_edit.textChanged.connect(self.on_user_range_changed)
        user_range_layout.addWidget(self.xmax_edit)
        user_range_layout.addStretch()
        self.user_range_widget.setVisible(False)
        xaxis_layout.addWidget(self.user_range_widget)
        
        results_layout.addWidget(xaxis_group)
        
        self.results_canvas = FigureCanvas(Figure(figsize=(10, 8)))
        results_layout.addWidget(self.results_canvas)
        
        tab_widget.addTab(results_tab, "Results")
        
        layout.addWidget(tab_widget)
        
        return panel
        
    def load_h5_file(self):
        """Load an H5 file and extract image datasets."""
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
            
    def on_h5_loaded(self, datasets):
        """Handle successful H5 file loading."""
        self.datasets = datasets
        self.progress_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        
        # Update dataset combo box with individual detection image datasets
        self.dataset_combo.clear()
        self.dataset_combo.addItems(list(datasets.keys()))
        
        # Enable buttons
        self.clear_ports_btn.setEnabled(True)
        self.marginal_btn.setEnabled(True)
        self.ratio_btn.setEnabled(True)
        
        # Load first dataset
        if datasets:
            self.on_dataset_changed(list(datasets.keys())[0])
            
    def on_load_error(self, error_msg):
        """Handle H5 file loading error."""
        self.progress_bar.setVisible(False)
        self.load_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", error_msg)
        
    def on_dataset_changed(self, dataset_key):
        """Handle dataset selection change."""
        if dataset_key in self.datasets:
            self.current_dataset_key = dataset_key
            self.current_image_index = 0
            self.load_current_image()
            self.update_navigation_buttons()
            
    def load_current_image(self):
        """Load the current image from the selected dataset."""
        if self.current_dataset_key and self.current_dataset_key in self.datasets:
            dataset_data = self.datasets[self.current_dataset_key]
            
            if len(dataset_data.shape) == 2:  # Single image
                image_data = dataset_data
                self.image_info_label.setText(f"Single Image: {self.current_dataset_key}")
                self.prev_btn.setEnabled(False)
                self.next_btn.setEnabled(False)
            else:  # Multiple images
                if self.current_image_index < dataset_data.shape[0]:
                    image_data = dataset_data[self.current_image_index]
                    self.image_info_label.setText(f"Image {self.current_image_index + 1}/{dataset_data.shape[0]}: {self.current_dataset_key}")
                else:
                    return
                    
            self.canvas.load_image(image_data, f"Dataset: {self.current_dataset_key}")
            
    def previous_image(self):
        """Load previous image in dataset."""
        if self.current_dataset_key and self.current_dataset_key in self.datasets:
            dataset_data = self.datasets[self.current_dataset_key]
            if len(dataset_data.shape) == 3 and self.current_image_index > 0:
                self.current_image_index -= 1
                self.load_current_image()
                self.update_navigation_buttons()
                
    def next_image(self):
        """Load next image in dataset."""
        if self.current_dataset_key and self.current_dataset_key in self.datasets:
            dataset_data = self.datasets[self.current_dataset_key]
            if len(dataset_data.shape) == 3 and self.current_image_index < dataset_data.shape[0] - 1:
                self.current_image_index += 1
                self.load_current_image()
                self.update_navigation_buttons()
                
    def update_navigation_buttons(self):
        """Update navigation button states."""
        if self.current_dataset_key and self.current_dataset_key in self.datasets:
            dataset_data = self.datasets[self.current_dataset_key]
            if len(dataset_data.shape) == 3:  # Multiple images
                self.prev_btn.setEnabled(self.current_image_index > 0)
                self.next_btn.setEnabled(self.current_image_index < dataset_data.shape[0] - 1)
            else:  # Single image
                self.prev_btn.setEnabled(False)
                self.next_btn.setEnabled(False)
                
    def on_ports_changed(self):
        """Handle when ports are added or removed."""
        self.update_ports_list()
        has_ports = len(self.canvas.ports) > 0
        self.calculate_ratio_btn.setEnabled(has_ports)
        self.apply_to_all_btn.setEnabled(has_ports and len(self.ratios) > 0)
        self.refresh_ports_btn.setEnabled(has_ports)
        
    def update_ports_list(self):
        """Update the ports list display."""
        self.ports_list.clear()
        for port in self.canvas.ports:
            x, y, width, height = port['bounds']
            # Calculate pixel count for this port
            pixel_count = self.canvas.get_port_pixel_sum(port['id'])
            item = QListWidgetItem(f"Port {port['id']}: ({x},{y}) {width}x{height} | Pixels: {pixel_count}")
            self.ports_list.addItem(item)
            
    def clear_ports(self):
        """Clear all defined ports and related analysis."""
        self.canvas.clear_ports()
        self.update_ports_list()
        
        # Clear marginal distributions tab
        self.marginal_canvas.figure.clear()
        self.marginal_canvas.draw()
        
        # Clear ratio analysis tab
        self.ratio_text.clear()
        
        # Clear results tab
        self.results_canvas.figure.clear()
        self.results_canvas.draw()
        
        # Clear stored ratios
        self.ratios.clear()
        
        # Update button states
        self.on_ports_changed()
        
    def on_xaxis_changed(self, xaxis_type):
        """Handle x-axis type change."""
        if xaxis_type == "User Defined":
            self.user_range_widget.setVisible(True)
        else:
            self.user_range_widget.setVisible(False)
            
        # Replot if we have results
        if hasattr(self, 'last_plot_results') and self.last_plot_results:
            self.plot_ratio_analysis(self.last_plot_results)
    
    def on_user_range_changed(self):
        """Handle user-defined range changes."""
        # Only replot if User Defined is selected and we have results
        if (self.xaxis_combo.currentText() == "User Defined" and 
            hasattr(self, 'last_plot_results') and self.last_plot_results):
            self.plot_ratio_analysis(self.last_plot_results)
        
    def plot_marginal_distributions(self):
        """Plot marginal distributions for all ports."""
        if not self.canvas.ports:
            QMessageBox.warning(self, "No Ports", "Please define some ports first.")
            return
            
        # Clear previous plot
        self.marginal_canvas.figure.clear()
        
        num_ports = len(self.canvas.ports)
        if num_ports == 0:
            return
            
        # Create subplots
        rows = (num_ports + 1) // 2
        cols = 2
        
        for i, port in enumerate(self.canvas.ports):
            ax = self.marginal_canvas.figure.add_subplot(rows, cols, i + 1)
            
            port_data = self.canvas.get_port_data(port['id'])
            if port_data is not None:
                # X marginal (sum along Y axis)
                x_marginal = np.sum(port_data, axis=0)
                # Y marginal (sum along X axis)
                y_marginal = np.sum(port_data, axis=1)
                
                # Plot both marginals
                x_pos = np.arange(len(x_marginal))
                y_pos = np.arange(len(y_marginal))
                
                ax.plot(x_pos, x_marginal, 'b-', label='X marginal', linewidth=2)
                ax.plot(y_pos, y_marginal, 'r-', label='Y marginal', linewidth=2)
                ax.set_title(f'Port {port["id"]} Marginal Distributions')
                ax.set_xlabel('Position')
                ax.set_ylabel('Intensity')
                ax.legend()
                ax.grid(True, alpha=0.3)
        
        self.marginal_canvas.figure.tight_layout()
        self.marginal_canvas.draw()
        
    def define_ratio(self):
        """Define a ratio calculation with checkbox selection for ports."""
        if len(self.canvas.ports) < 1:
            QMessageBox.warning(self, "No Ports", "Need at least 1 port to define a ratio.")
            return
            
        # Create dialog for ratio definition
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, 
                                    QLabel, QCheckBox, QGroupBox, QScrollArea, QWidget)
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Define Ratio")
        dialog.setModal(True)
        dialog.resize(400, 500)
        
        layout = QVBoxLayout(dialog)
        
        # Create scroll area for port selection
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Numerator selection group
        num_group = QGroupBox("Numerator Ports")
        num_layout = QVBoxLayout(num_group)
        self.numerator_checkboxes = []
        
        for port in self.canvas.ports:
            checkbox = QCheckBox(f"Port {port['id']}")
            self.numerator_checkboxes.append(checkbox)
            num_layout.addWidget(checkbox)
            
        scroll_layout.addWidget(num_group)
        
        # Denominator selection group
        denom_group = QGroupBox("Denominator Ports")
        denom_layout = QVBoxLayout(denom_group)
        self.denominator_checkboxes = []
        
        for port in self.canvas.ports:
            checkbox = QCheckBox(f"Port {port['id']}")
            self.denominator_checkboxes.append(checkbox)
            denom_layout.addWidget(checkbox)
            
        scroll_layout.addWidget(denom_group)
        
        # Ratio preview
        preview_label = QLabel("Ratio Preview: (select ports above)")
        preview_label.setStyleSheet("font-weight: bold; color: blue;")
        scroll_layout.addWidget(preview_label)
        
        # Connect checkboxes to update preview
        for checkbox in self.numerator_checkboxes + self.denominator_checkboxes:
            checkbox.toggled.connect(lambda: self.update_ratio_preview(preview_label))
            
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            # Get selected numerator ports
            numerator_ports = []
            for i, checkbox in enumerate(self.numerator_checkboxes):
                if checkbox.isChecked():
                    numerator_ports.append(self.canvas.ports[i]['id'])
                    
            # Get selected denominator ports
            denominator_ports = []
            for i, checkbox in enumerate(self.denominator_checkboxes):
                if checkbox.isChecked():
                    denominator_ports.append(self.canvas.ports[i]['id'])
                    
            if not numerator_ports:
                QMessageBox.warning(self, "No Numerator", "Please select at least one port for the numerator.")
                return
                
            if not denominator_ports:
                QMessageBox.warning(self, "No Denominator", "Please select at least one port for the denominator.")
                return
                
            # Create ratio definition
            ratio_def = {
                'numerator_ports': numerator_ports,
                'denominator_ports': denominator_ports,
                'description': self.generate_ratio_description(numerator_ports, denominator_ports)
            }
                
            self.ratios.append(ratio_def)
            self.update_ratio_display()
            self.apply_to_all_btn.setEnabled(len(self.canvas.ports) > 0 and len(self.ratios) > 0)
            
    def update_ratio_preview(self, preview_label):
        """Update the ratio preview as user selects ports."""
        numerator_ports = []
        for i, checkbox in enumerate(self.numerator_checkboxes):
            if checkbox.isChecked():
                numerator_ports.append(self.canvas.ports[i]['id'])
                
        denominator_ports = []
        for i, checkbox in enumerate(self.denominator_checkboxes):
            if checkbox.isChecked():
                denominator_ports.append(self.canvas.ports[i]['id'])
                
        if numerator_ports and denominator_ports:
            description = self.generate_ratio_description(numerator_ports, denominator_ports)
            preview_label.setText(f"Ratio Preview: {description}")
        else:
            preview_label.setText("Ratio Preview: (select ports above)")
            
    def generate_ratio_description(self, numerator_ports, denominator_ports):
        """Generate a human-readable description of the ratio."""
        if len(numerator_ports) == 1:
            num_desc = f"Port {numerator_ports[0]}"
        else:
            num_desc = "(" + " + ".join([f"Port {p}" for p in numerator_ports]) + ")"
            
        if len(denominator_ports) == 1:
            denom_desc = f"Port {denominator_ports[0]}"
        else:
            denom_desc = "(" + " + ".join([f"Port {p}" for p in denominator_ports]) + ")"
            
        return f"{num_desc} / {denom_desc}"
            
    def update_ratio_display(self):
        """Update the ratio analysis display."""
        if not self.ratios:
            self.ratio_text.setText("No ratios defined.")
            return
            
        text = "Defined Ratios:\n\n"
        for i, ratio in enumerate(self.ratios):
            text += f"{i+1}. {ratio['description']}\n"
            
        self.ratio_text.setText(text)
        
    def calculate_ratios(self):
        """Calculate all defined ratios for the current image."""
        if not self.ratios:
            QMessageBox.information(self, "No Ratios", "Please define some ratios first.")
            return
            
        if not self.canvas.ports:
            QMessageBox.warning(self, "No Ports", "Please define some ports first.")
            return
            
        results = f"Ratio Analysis for {self.current_dataset_key}:\n"
        results += "=" * 50 + "\n\n"
        
        for i, ratio in enumerate(self.ratios):
            # Calculate numerator sum
            numerator_sum = 0
            numerator_breakdown = []
            for port_id in ratio['numerator_ports']:
                port_sum = self.canvas.get_port_pixel_sum(port_id)
                numerator_sum += port_sum
                numerator_breakdown.append(f"Port {port_id}: {port_sum:.2f}")
                
            # Calculate denominator sum
            denominator_sum = 0
            denominator_breakdown = []
            for port_id in ratio['denominator_ports']:
                port_sum = self.canvas.get_port_pixel_sum(port_id)
                denominator_sum += port_sum
                denominator_breakdown.append(f"Port {port_id}: {port_sum:.2f}")
                
            # Calculate ratio
            if denominator_sum > 0:
                ratio_value = numerator_sum / denominator_sum
                results += f"Ratio {i+1}: {ratio['description']}\n"
                results += f"  Numerator sum: {numerator_sum:.2f} = {' + '.join([str(self.canvas.get_port_pixel_sum(pid)) for pid in ratio['numerator_ports']])}\n"
                results += f"  Denominator sum: {denominator_sum:.2f} = {' + '.join([str(self.canvas.get_port_pixel_sum(pid)) for pid in ratio['denominator_ports']])}\n"
                results += f"  Ratio: {ratio_value:.4f}\n\n"
                
                # Show individual port contributions
                results += "  Numerator breakdown:\n"
                for port_id in ratio['numerator_ports']:
                    port_sum = self.canvas.get_port_pixel_sum(port_id)
                    results += f"    Port {port_id}: {port_sum:.2f}\n"
                    
                results += "  Denominator breakdown:\n"
                for port_id in ratio['denominator_ports']:
                    port_sum = self.canvas.get_port_pixel_sum(port_id)
                    results += f"    Port {port_id}: {port_sum:.2f}\n"
                results += "\n"
            else:
                results += f"Ratio {i+1}: {ratio['description']}\n"
                results += f"  Error: Division by zero (denominator sum = 0)\n\n"
                
        self.ratio_text.setText(results)
        
    def apply_ratios_to_all(self):
        """Apply defined ratios to all detection image datasets and plot results."""
        if not self.ratios:
            QMessageBox.information(self, "No Ratios", "Please define some ratios first.")
            return
            
        if not self.canvas.ports:
            QMessageBox.warning(self, "No Ports", "Please define some ports first.")
            return
            
        if not self.datasets:
            QMessageBox.warning(self, "No Datasets", "No detection image datasets available.")
            return
            
        # Get all detection image datasets and sort them numerically
        detection_datasets = []
        for key, data in self.datasets.items():
            if 'datasets/detection.images' in key:
                detection_datasets.append((key, data))
                
        if not detection_datasets:
            QMessageBox.warning(self, "No Detection Datasets", "No detection image datasets found.")
            return
            
        # Sort datasets by their numeric suffix (e.g., images.0, images.1, images.10, images.11)
        def extract_number(key):
            # Extract the number after the last dot
            parts = key.split('.')
            if len(parts) >= 2:
                try:
                    return int(parts[-1])
                except ValueError:
                    return 0
            return 0
            
        detection_datasets.sort(key=lambda x: extract_number(x[0]))
        
        # Debug: Print the sorted order
        print("Processing datasets in order:")
        for key, data in detection_datasets:
            print(f"  {key} (shape: {data.shape})")
            
        # Calculate total number of images across all datasets
        total_images = 0
        for key, data in detection_datasets:
            if len(data.shape) == 2:  # Single image
                total_images += 1
            elif len(data.shape) == 3:  # Multiple images
                total_images += data.shape[0]
                
        if total_images == 0:
            QMessageBox.information(self, "No Images", "No images found in detection datasets.")
            return
            
        # Calculate ratios for all images across all datasets
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total_images)
        
        results = []
        image_counter = 0
        
        for dataset_key, dataset_data in detection_datasets:
            if len(dataset_data.shape) == 2:  # Single image
                # Process single image
                rotated_image = np.rot90(dataset_data, k=-1)
                image_results = self.calculate_ratios_for_image(rotated_image, image_counter, dataset_key)
                results.append(image_results)
                image_counter += 1
                self.progress_bar.setValue(image_counter)
                QApplication.processEvents()
                
            elif len(dataset_data.shape) == 3:  # Multiple images
                # Process multiple images
                for image_idx in range(dataset_data.shape[0]):
                    rotated_image = np.rot90(dataset_data[image_idx], k=-1)
                    image_results = self.calculate_ratios_for_image(rotated_image, image_counter, dataset_key, image_idx)
                    results.append(image_results)
                    image_counter += 1
                    self.progress_bar.setValue(image_counter)
                    QApplication.processEvents()
                    
        self.progress_bar.setVisible(False)
        
        # Plot results
        self.plot_ratio_analysis(results)
        
    def calculate_ratios_for_image(self, rotated_image, image_number, dataset_key, image_idx=None):
        """Calculate ratios for a single image."""
        image_results = {
            'image_number': image_number,
            'dataset_key': dataset_key,
            'image_idx': image_idx
        }
        ratio_values = []
        
        for ratio in self.ratios:
            # Calculate numerator sum
            numerator_sum = 0
            for port_id in ratio['numerator_ports']:
                port_data = self.get_port_data_from_image(rotated_image, port_id)
                if port_data is not None:
                    numerator_sum += np.sum(port_data)
                    
            # Calculate denominator sum
            denominator_sum = 0
            for port_id in ratio['denominator_ports']:
                port_data = self.get_port_data_from_image(rotated_image, port_id)
                if port_data is not None:
                    denominator_sum += np.sum(port_data)
                    
            # Calculate ratio
            if denominator_sum > 0:
                ratio_value = numerator_sum / denominator_sum
            else:
                ratio_value = 0  # or np.nan
                
            ratio_values.append({
                'description': ratio['description'],
                'value': ratio_value,
                'numerator_sum': numerator_sum,
                'denominator_sum': denominator_sum
            })
            
        image_results['ratios'] = ratio_values
        return image_results
        
    def get_port_data_from_image(self, image_data, port_id):
        """Get pixel data for a specific port from a given image."""
        for port in self.canvas.ports:
            if port['id'] == port_id:
                x, y, width, height = port['bounds']
                # Ensure coordinates are within image bounds
                x = max(0, min(x, image_data.shape[1] - 1))
                y = max(0, min(y, image_data.shape[0] - 1))
                width = min(width, image_data.shape[1] - x)
                height = min(height, image_data.shape[0] - y)
                
                return image_data[y:y+height, x:x+width]
        return None
        
    def get_scan_parameter_values(self, results):
        """Try to extract scan parameter values from H5 file."""
        # For now, return image numbers as fallback
        # In a real implementation, you would look for scan parameters in the H5 file
        # This could be in datasets like 'scan/parameter' or similar
        print("Scan parameter extraction not implemented yet, using image numbers")
        return [r['image_number'] for r in results]
        
    def plot_ratio_analysis(self, results):
        """Plot ratio values versus selected x-axis in the Results tab."""
        if not results:
            return
            
        # Store results for replotting
        self.last_plot_results = results
            
        # Clear previous plot
        self.results_canvas.figure.clear()
        
        # Get x-axis values based on selection
        xaxis_type = self.xaxis_combo.currentText()
        if xaxis_type == "Index":
            x_values = [r['image_number'] for r in results]
            x_label = "Image Number"
        elif xaxis_type == "Scan Parameter":
            # Try to find scan parameter in H5 file
            x_values = self.get_scan_parameter_values(results)
            x_label = "Scan Parameter"
        elif xaxis_type == "User Defined":
            try:
                xmin = float(self.xmin_edit.text())
                xmax = float(self.xmax_edit.text())
                x_values = np.linspace(xmin, xmax, len(results))
                x_label = "User Defined"
            except ValueError:
                QMessageBox.warning(self, "Invalid Range", "Please enter valid numeric values for min and max.")
                return
        else:
            x_values = [r['image_number'] for r in results]
            x_label = "Image Number"
            
        num_ratios = len(self.ratios)
        
        if num_ratios == 1:
            # Single ratio - simple plot
            ax = self.results_canvas.figure.add_subplot(111)
            ratio_values = [r['ratios'][0]['value'] for r in results]
            ax.plot(x_values, ratio_values, 'b-o', linewidth=2, markersize=4)
            ax.set_xlabel(x_label)
            ax.set_ylabel('Relative Population')
            ax.set_title(f'Relative Population vs {x_label}\n{self.ratios[0]["description"]}')
            ax.grid(True, alpha=0.3)
        else:
            # Multiple ratios - subplots
            rows = (num_ratios + 1) // 2
            cols = 2
            
            for i, ratio in enumerate(self.ratios):
                ax = self.results_canvas.figure.add_subplot(rows, cols, i + 1)
                ratio_values = [r['ratios'][i]['value'] for r in results]
                ax.plot(x_values, ratio_values, 'b-o', linewidth=2, markersize=4)
                ax.set_xlabel(x_label)
                ax.set_ylabel('Relative Population')
                ax.set_title(f'Ratio {i+1}: {ratio["description"]}')
                ax.grid(True, alpha=0.3)
                
                # Add statistics
                mean_val = np.mean(ratio_values)
                std_val = np.std(ratio_values)
                ax.text(0.02, 0.98, f'Mean: {mean_val:.4f} ± {std_val:.4f}', 
                        transform=ax.transAxes, verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
        
        self.results_canvas.figure.tight_layout()
        self.results_canvas.draw()
        
        # Update ratio text with summary
        summary = f"Ratio Analysis Summary - All Detection Images:\n"
        summary += "=" * 60 + "\n\n"
        summary += f"Analyzed {len(results)} images across all detection datasets with {num_ratios} ratios each.\n\n"
        
        # Group by dataset for better organization
        dataset_groups = {}
        for result in results:
            dataset_key = result['dataset_key']
            if dataset_key not in dataset_groups:
                dataset_groups[dataset_key] = []
            dataset_groups[dataset_key].append(result)
            
        summary += "Datasets analyzed (in order):\n"
        # Sort dataset groups by their numeric suffix for display
        def extract_number_for_display(key):
            parts = key.split('.')
            if len(parts) >= 2:
                try:
                    return int(parts[-1])
                except ValueError:
                    return 0
            return 0
        sorted_dataset_groups = sorted(dataset_groups.items(), key=lambda x: extract_number_for_display(x[0]))
        for dataset_key, dataset_results in sorted_dataset_groups:
            summary += f"  {dataset_key}: {len(dataset_results)} images\n"
        summary += "\n"
        
        for i, ratio in enumerate(self.ratios):
            ratio_values = [r['ratios'][i]['value'] for r in results]
            mean_val = np.mean(ratio_values)
            std_val = np.std(ratio_values)
            min_val = np.min(ratio_values)
            max_val = np.max(ratio_values)
            
            summary += f"Ratio {i+1}: {ratio['description']}\n"
            summary += f"  Mean: {mean_val:.4f} ± {std_val:.4f}\n"
            summary += f"  Range: {min_val:.4f} - {max_val:.4f}\n\n"
            
        self.ratio_text.setText(summary)


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show main window
    window = ARTIQImageAnalyzer()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
