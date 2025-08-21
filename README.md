AI Finance Advisor

Working towards an AI-powered personal finance app that categorizes transactions, identifies spending habits/patterns, and provides potential money saving insights.

Features:
  - Smart Categorization: Automatically classifies transactions as Groceries, Rent, Subscriptions, etc. as well as Needs/Wants or Savings
  - Spending Insights: Detects recurring wants vs needs and highlights overspending and potential ways to cut back
  - Generates Advice: The AI engine aims to suggest cheaper alternatives for subscriptions, e.g, Netflix @ €12.99 p/m vs Prime Video @ €9.99 p/m
  - Habit Analysis: Projects long-term savings if daily wants are eliminated or achieved through cheaper means, daily coffee being made at home
                    rather than bought in a store every day
  - Investment Projection: Shows future value of redirected expenditure if savings on wants are redirected to the S&P500, using the historical values
                           of returns to calculate this number for future value of saving

Tech Stack:
  - Backend: FastAPI, SQLAlchemy, PostgreSQL, Redis
  - Frontend: Next.js(React), TailwindCSS
  - AI Engine: OpenAI gpt-4o-mini for enrichment and advice generation
  - Infrastructure: Docker & Docker Compose

How to Run:
  - Clone the repository: git clone https://github.com/roan44./ai-finance-advisor.git
                          cd ai-finance-advisor
  - Start services with Docker: docker compose up --build
  - Open application in browser: http://localhost:3000/transactions
  - API available at: http://loclahost:8000

Usage:
  - Add transactions through web app
  - Click enrich to categorize transactions with AI
  - Not yet ready but working on /advisor page for generation of personalised financial insights
