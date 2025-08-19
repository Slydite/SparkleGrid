
# GridSentinel: A High-Frequency IoT Data Pipeline for a Physical Microgrid

**A full-stack IoT platform designed to capture and process data from a physical microgrid at 1000Hz with sub-millisecond latency. This system successfully managed high-throughput writes of over 90 GB of data daily.**

> **Note:** This repository contains the V1 architecture for the `GridSentinel` project. Subsequent C++ performance optimizations were developed in a private research repository.

---

### The Challenge

Physical microgrids require real-time, high-frequency monitoring for stability analysis. The challenge was to build a custom platform capable of capturing sensor data at 1000Hz, a task that demands sub-millisecond processing latency and the ability to handle massive data volumes on a very constrained RaspberryPi.

### Architecture Overview

`GridSentinel` is a multi-component system designed for high-performance data ingestion at the edge and flexible visualization. The architecture is broken down into the following repositories:

*   **`sensor`:** Contains Python code for interfacing with the ADC and sensors, responsible for high-frequency data capture and direct database updates. Replaced with C++ in another repo (V2).
*   **`GridSense`:** The primary Django backend, providing a REST API for data access and management.
*   **`GridWatch`:** The Vue.js frontend for real-time data visualization and system monitoring.
*   **`GridSense_Cloud`:** A secondary Django service designed to aggregate data from multiple microgrid sites for broader analysis.
