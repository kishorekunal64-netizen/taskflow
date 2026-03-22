require('dotenv').config();
const express = require('express');
const { Pool } = require('pg');
const cors = require('cors');
const helmet = require('helmet');
const Joi = require('joi');

const app = express();

app.use(helmet());
app.use(cors());
app.use(express.json());

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  database: process.env.DB_NAME || 'taskflow_db',
  user: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'taskflow123'
});

const createTaskSchema = Joi.object({
  title: Joi.string().required().messages({
    'any.required': 'title is required',
    'string.empty': 'title is required'
  }),
  priority: Joi.string().valid('low', 'medium', 'high').default('medium').messages({
    'any.only': 'priority must be low, medium, or high'
  }),
  due_date: Joi.string().isoDate().allow(null, '').default(null)
});

// Health check
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'taskflow-api', version: '1.0.0' });
});

// GET all tasks
app.get('/api/tasks', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM tasks ORDER BY created_at DESC');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// POST create task
app.post('/api/tasks', async (req, res) => {
  const { error, value } = createTaskSchema.validate(req.body, { abortEarly: true });
  if (error) return res.status(400).json({ error: error.details[0].message });
  try {
    const result = await pool.query(
      'INSERT INTO tasks (title, priority, due_date) VALUES ($1, $2, $3) RETURNING *',
      [value.title, value.priority, value.due_date]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// PUT update task
app.put('/api/tasks/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const { title, done, priority, due_date } = req.body;
    const result = await pool.query(
      'UPDATE tasks SET title=$1, done=$2, priority=$3, due_date=$4 WHERE id=$5 RETURNING *',
      [title, done, priority, due_date, id]
    );
    if (result.rows.length === 0) return res.status(404).json({ error: 'Task not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// DELETE task
app.delete('/api/tasks/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query('DELETE FROM tasks WHERE id=$1 RETURNING *', [id]);
    if (result.rows.length === 0) return res.status(404).json({ error: 'Task not found' });
    res.json({ message: 'Task deleted', task: result.rows[0] });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`TaskFlow API running → http://localhost:${PORT}`);
});

module.exports = app;