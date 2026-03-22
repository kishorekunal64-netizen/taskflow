const express = require('express');
const { Pool } = require('pg');

const app = express();
app.use(express.json());

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  database: process.env.DB_NAME || 'taskflow_db',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'taskflow123'
});

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'taskflow-api', version: '1.0.0' });
});

app.get('/api/tasks', async (req, res) => {
  const result = await pool.query('SELECT * FROM tasks ORDER BY created_at DESC');
  res.json(result.rows);
});

app.listen(3000, () => {
  console.log('TaskFlow API running → http://localhost:3000');
});

module.exports = app;