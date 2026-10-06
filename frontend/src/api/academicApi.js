import client from './client';

export const academicApi = {
  getDepartments: (params = {}) => client.get('/academic/departments/', { params }),
  getPrograms: (params = {}) => client.get('/academic/programs/', { params }),
  getSemesters: (params = {}) => client.get('/academic/semesters/', { params }),
  getDivisions: (params = {}) => client.get('/academic/divisions/', { params }),
  createDivision: (data) => client.post('/academic/divisions/', data),
  updateDivision: (id, data) => client.patch(`/academic/divisions/${id}/`, data),
  deleteDivision: (id) => client.delete(`/academic/divisions/${id}/`),
  assignStudents: (id, data) => client.post(`/academic/divisions/${id}/assign-students/`, data),
  getDivisionSubjects: (id) => client.get(`/academic/divisions/${id}/subjects/`),
  getLabBatches: (params = {}) => client.get('/academic/lab-batches/', { params }),
  createLabBatch: (data) => client.post('/academic/lab-batches/', data),
  getAcademicYears: (params = {}) => client.get('/academic/years/', { params }),
  createAcademicYear: (data) => client.post('/academic/years/', data),
  getCurrentContext: () => client.get('/academic/contexts/current/'),
};

export default academicApi;
