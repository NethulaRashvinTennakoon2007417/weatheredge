# WeatherEdge Project Overview & Context for Claude

This document provides a comprehensive overview of the **WeatherEdge Analyzer** project to help Claude continue the development and improvement of the website.

## 1. Project Vision
**WeatherEdge** is a professional-grade quantitative intelligence tool designed for traders on prediction markets (specifically **Polymarket**) who trade weather-based contracts. It transforms complex meteorological data into actionable betting signals by using statistical models and a Bayesian consensus engine.

## 2. Core Value Proposition
- **Edge Intelligence**: Identifying when market prices (odds) deviate significantly from model-predicted probabilities.
- **Bayesian Consensus**: Filtering out meteorological "noise" by comparing multiple models (GEM, HRRR, ICON, NWS).
- **Risk Management**: Providing exact **Kelly Criterion** bankroll sizing based on model conviction.
- **Probabilistic Forecasting**: Using ECMWF ensemble members (50 members) to visualize probability distributions (P10, median, P90) rather than simple point forecasts.

## 3. Current Technical Stack
- **Frontend Framework**: Vite + React 19
- **Animations**: Framer Motion
- **Visuals/3D**: Three.js & @react-three/fiber (used for the background `WeatherScene`)
- **Icons**: Lucide-React
- **Styling**: Vanilla CSS with a focus on:
    - **Dark Mode**: Sleek, professional aesthetic (`#0f1115` background).
    - **Glassmorphism**: Translucent cards with backdrop filters and subtle borders.
    - **Typography**: Inter (Google Font).
    - **Responsiveness**: Basic mobile support implemented.

## 4. Implemented UI Components (so far)
- **Hero Section**: High-impact entrance with a 3D weather scene background and clear CTA.
- **Features Section**: Grid layout showcasing the 4 core pillars (Conviction Meter, Model Mosaic, Ensemble Distribution, Edge Detection).
- **Reviews Section**: Social proof through user testimonials.
- **Pricing Section**: Subscription model ($97/lifetime) with a cryptocurrency payment UI (USDT/Solana).

## 5. Directory Structure
```text
WeatherEdge/
├── WEB/                    # Frontend React Project
│   ├── src/
│   │   ├── components/     # UI Components (Hero, Features, etc.)
│   │   ├── App.jsx         # Main Layout
│   │   ├── index.css       # Design System & Global Styles
│   │   └── main.jsx        # Entry point
│   ├── package.json        # Dependencies
│   └── vite.config.js      # Build config
├── app/                    # Backend/Core Logic (Python)
├── launch.py               # Application launcher
└── requirements.txt        # Backend dependencies
```

## 6. Current State & Known Areas for Improvement
The current website is a high-quality **landing page**, but it lacks the actual "tooling" interface. 
- **The "WOW" Factor**: While the design is clean, it could be more dynamic. The 3D scene is a great start, but the cards could use more interactive depth.
- **Visual Demonstrations**: The features (Conviction Meter, etc.) are currently just text and icons. They should ideally be represented by interactive UI mockups or mini-dashboards to show *how* the data looks.
- **Conversion Path**: The "Get Access Now" button scrolls to pricing, but the payment flow is static (manual QR/Address).
- **Dashboard Integration**: There is currently no "Logged In" or "App" view where a user would actually see the weather signals.

## 7. Context from Previous Development
The project was previously worked on by Gemini 3.1 Pro. The user feels the design is "ok" but wants Claude to take it to the next level of "Premium" and "Wowed" aesthetics, potentially adding more interactive elements or refining the existing layout to feel like a high-end quant platform.

---
**Goal for Claude**: Improve the aesthetics, refine the components, and prepare the site to feel like a premium, state-of-the-art fintech product.
