import client from './client';

export const studentApi = {
  /**
   * List students with scope-aware filtering and search.
   */
  getStudents: (params = {}) => client.get('/students/', { params }),

  /**
   * Retrieve full composed profile of a student.
   */
  getStudentProfile: (id) => client.get(`/students/${id}/`),

  /**
   * Retrieve current authenticated student's own profile.
   */
  getMyProfile: () => client.get('/students/me/'),

  /**
   * Update own profile (student self-service).
   * Backend whitelists editable fields; identifiers, admission data,
   * Aadhaar number and verified documents are always locked.
   */
  updateMyProfile: (data) => client.patch('/students/me/update/', data),

  /**
   * One-time permanent lock. After this the student cannot edit or
   * self-upload again. Staff unlock is the only recourse.
   */
  lockMyProfile: () => client.post('/students/me/lock/', {}),

  /**
   * Reveal unmasked sensitive details (requires permission + audit reason).
   */
  revealSensitive: (id, reason) =>
    client.post(`/students/${id}/reveal/`, { reason }),

  /**
   * Assign or edit a student's division and/or lab batch (HOD/Admin authority).
   */
  assignDivision: (id, payload) => {
    const body = typeof payload === 'object' && payload !== null ? payload : { division_id: payload };
    return client.post(`/students/${id}/assign-division/`, body);
  },

  /**
   * Staff/HOD unlock of a locked student profile (recourse for one more edit).
   * Server enforces department scoping for HODs; reason is mandatory and audited.
   */
  unlockStudentProfile: (id, reason) =>
    client.post(`/students/${id}/unlock/`, { reason }),

  /**
   * Staff/HOD password reset typed by the caller (department-scoped on server).
   * The student is forced to change the password at next login.
   * Body: { new_password, reason }. The password is never echoed back.
   */
  resetStudentPassword: (id, payload) =>
    client.post(`/students/${id}/reset-password/`, payload),

  // ─── Student documents (photo / signature / allotment / marksheets) ───
  // Size policy: ALLOTMENT_LETTER max 200 KB, all others max 150 KB (enforced server-side too).
  documentSizeLimits: {
    ALLOTMENT_LETTER: 200 * 1024,
    DEFAULT: 150 * 1024,
  },
  documentLimitFor: (docType) =>
    docType === 'ALLOTMENT_LETTER' ? 200 * 1024 : 150 * 1024,

  /**
   * Student self-upload: POST /students/me/documents/upload/ (multipart).
   */
  uploadMyDocument: (file, documentType, title = '') => {
    const form = new FormData();
    form.append('file', file);
    form.append('document_type', documentType);
    if (title) form.append('title', title);
    return client.post('/students/me/documents/upload/', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  /**
   * Staff upload on behalf of a student: POST /students/:id/documents/upload/
   */
  uploadStudentDocument: (id, file, documentType, title = '') => {
    const form = new FormData();
    form.append('file', file);
    form.append('document_type', documentType);
    if (title) form.append('title', title);
    return client.post(`/students/${id}/documents/upload/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  /**
   * List documents: own (/me) or staff view (/:id).
   */
  listMyDocuments: () => client.get('/students/me/documents/'),
  listStudentDocuments: (id) => client.get(`/students/${id}/documents/`),

  /**
   * Download helpers (blob). Use `responseType: 'blob'` and open/save client-side.
   */
  downloadMyDocument: (docId) =>
    client.get(`/students/me/documents/${docId}/download/`, { responseType: 'blob' }),
  downloadStudentDocument: (id, docId) =>
    client.get(`/students/${id}/documents/${docId}/download/`, { responseType: 'blob' }),

  /**
   * Delete / reset (student own, or staff reset e.g. wrong allotment letter).
   */
  deleteMyDocument: (docId) => client.delete(`/students/me/documents/${docId}/`),
  deleteStudentDocument: (id, docId) => client.delete(`/students/${id}/documents/${docId}/`),
};

export default studentApi;
