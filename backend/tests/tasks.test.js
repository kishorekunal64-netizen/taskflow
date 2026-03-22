const request = require('supertest');
const app = require('../server');
const fc = require('fast-check');

describe('TaskFlow API', () => {

  test('GET /api/health returns ok', async () => {
    const res = await request(app).get('/api/health');
    expect(res.statusCode).toBe(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.service).toBe('taskflow-api');
  });

  test('GET /api/tasks returns array', async () => {
    const res = await request(app).get('/api/tasks');
    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });

  test('POST /api/tasks creates a task', async () => {
    const res = await request(app)
      .post('/api/tasks')
      .send({ title: 'Test task from Jest', priority: 'medium' });
    expect(res.statusCode).toBe(201);
    expect(res.body.title).toBe('Test task from Jest');
    expect(res.body.id).toBeDefined();
  });

  test('POST /api/tasks fails without title', async () => {
    const res = await request(app)
      .post('/api/tasks')
      .send({ priority: 'high' });
    expect(res.statusCode).toBe(400);
    expect(res.body.error).toBe('title is required');
  });

  test('DELETE /api/tasks/:id deletes a task', async () => {
    const create = await request(app)
      .post('/api/tasks')
      .send({ title: 'Task to delete', priority: 'low' });
    const id = create.body.id;
    const res = await request(app).delete(`/api/tasks/${id}`);
    expect(res.statusCode).toBe(200);
    expect(res.body.message).toBe('Task deleted');
  });

  // Task 4.1 — invalid priority returns 400
  test('POST /api/tasks with invalid priority returns 400', async () => {
    const res = await request(app)
      .post('/api/tasks')
      .send({ title: 'x', priority: 'urgent' });
    expect(res.statusCode).toBe(400);
    expect(res.body.error).toBe('priority must be low, medium, or high');
  });

});

// Property-based tests — require live PostgreSQL connection
// Feature: create-task, Property 1: valid task creation round-trip
// Validates: Requirements 1.1, 3.1, 3.2
test('Property 1: valid task creation round-trip', async () => {
  jest.setTimeout(30000);
  await fc.assert(fc.asyncProperty(
    fc.record({ title: fc.string({ minLength: 1 }), priority: fc.constantFrom('low', 'medium', 'high') }),
    async ({ title, priority }) => {
      const res = await request(app).post('/api/tasks').send({ title, priority });
      return res.status === 201 && res.body.title === title && res.body.id !== undefined && res.body.created_at !== undefined;
    }
  ), { numRuns: 100 });
}, 30000);

// Feature: create-task, Property 2: default field values
// Validates: Requirements 1.2, 1.3
test('Property 2: default field values', async () => {
  await fc.assert(fc.asyncProperty(
    fc.string({ minLength: 1 }),
    async (title) => {
      const res = await request(app).post('/api/tasks').send({ title });
      return res.status === 201 && res.body.priority === 'medium' && res.body.due_date === null;
    }
  ), { numRuns: 100 });
}, 30000);

// Feature: create-task, Property 3: missing title rejected without DB write
// Validates: Requirements 2.1, 2.3
test('Property 3: missing title rejected without DB write', async () => {
  await fc.assert(fc.asyncProperty(
    fc.record({ priority: fc.constantFrom('low', 'medium', 'high') }),
    async (body) => {
      const before = (await request(app).get('/api/tasks')).body.length;
      const res = await request(app).post('/api/tasks').send(body);
      const after = (await request(app).get('/api/tasks')).body.length;
      return res.status === 400 && res.body.error === 'title is required' && before === after;
    }
  ), { numRuns: 100 });
}, 30000);

// Feature: create-task, Property 4: invalid priority rejected without DB write
// Validates: Requirements 2.2, 2.3
test('Property 4: invalid priority rejected without DB write', async () => {
  await fc.assert(fc.asyncProperty(
    fc.tuple(
      fc.string({ minLength: 1 }),
      fc.string({ minLength: 1 }).filter(s => !['low', 'medium', 'high'].includes(s))
    ),
    async ([title, priority]) => {
      const before = (await request(app).get('/api/tasks')).body.length;
      const res = await request(app).post('/api/tasks').send({ title, priority });
      const after = (await request(app).get('/api/tasks')).body.length;
      return res.status === 400 && res.body.error === 'priority must be low, medium, or high' && before === after;
    }
  ), { numRuns: 100 });
}, 30000);