import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import academicApi from '../../api/academicApi';
import studentApi from '../../api/studentApi';
import facultyApi from '../../api/facultyApi';
import curriculumApi from '../../api/curriculumApi';
import { LoadingState, ErrorState } from '../../components/common/StateDisplays';
import PageHeader from '../../components/common/PageHeader';
import Modal from '../../components/common/Modal';
import {
  Bell,
  Plus,
  Users,
  ChevronDown,
  ChevronRight,
  Pencil,
  Check,
  Search,
  BookOpen,
} from 'lucide-react';

function divisionLetter(i) {
  return String.fromCharCode(65 + i);
}

const YEAR_NAMES = { 1: 'First Year (FY)', 2: 'Second Year (SY)', 3: 'Third Year (TY)', 4: 'Final Year' };

function semLabel(semesters, semNumber) {
  const s = semesters.find((x) => Number(x.number) === Number(semNumber));
  const yearName = YEAR_NAMES[Number(s?.year_level)] || '';
  const term = (s?.term_type || '').toUpperCase() === 'EVEN' ? 'Even' : 'Odd';
  return `${yearName ? `${yearName} ` : ''}Sem ${semNumber} (${term})`;
}

// One teacher cell used by every row of the teachers popup: assigned shows
// just "✓ name" + pencil; unassigned (or editing) shows the faculty dropdown
// directly and saves on pick — no intermediate Set button.
function TeacherCell({ holderLabel, editing, value, faculties, saving, placeholder, onEdit, onPick }) {
  if (holderLabel && !editing) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
        <span
          style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
            background: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0',
            borderRadius: '9999px', padding: '0.2rem 0.65rem',
            fontSize: '0.75rem', fontWeight: 700,
          }}
        >
          <Check size={12} /> {holderLabel}
        </span>
        <button
          type="button"
          title="Edit teacher"
          onClick={onEdit}
          style={{
            background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px',
            padding: '0.25rem', cursor: 'pointer', display: 'inline-flex', color: '#475569',
          }}
        >
          <Pencil size={13} />
        </button>
      </span>
    );
  }
  return (
    <select
      className="edvana-input"
      value={value || ''}
      disabled={!!saving}
      onChange={(e) => { if (e.target.value) onPick(e.target.value); }}
      style={{ height: '32px', fontSize: '0.78rem', minWidth: '190px' }}
      title={placeholder}
    >
      <option value="">{saving ? 'Saving…' : placeholder}</option>
      {faculties.map((f) => (
        <option key={f.id} value={f.id}>
          {f.display_name || f.name || f.username || f.employee_code}
        </option>
      ))}
    </select>
  );
}

export default function HODDivisionsBatchesPage() {
  const { user, hasRole } = useAuth();
  const isSysadmin = hasRole('SYSADMIN') || hasRole('ADMIN_HEAD');
  const isHOD = hasRole('HOD') && !isSysadmin;
  const canManage = isSysadmin || isHOD;

  const hodRole = user?.roles?.find((r) => r.codename === 'HOD');
  const hodDeptId = hodRole?.department_id;

  const [departments, setDepartments] = useState([]);
  const [years, setYears] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [divisions, setDivisions] = useState([]);
  const [students, setStudents] = useState([]);
  const [faculties, setFaculties] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);
  const [actionError, setActionError] = useState(null);

  const [selectedDept, setSelectedDept] = useState('');

  // Class cards + subject teachers + merge flow
  const [expandedDivId, setExpandedDivId] = useState(null);
  const [divDetail, setDivDetail] = useState({}); // { [divId]: { subjects, assignments, scheme } }
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [slotEdit, setSlotEdit] = useState({}); // { [subjectId]: facultyId } edit mode
  const [savingSlot, setSavingSlot] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    academic_year: '', semester: '', name: 'A', seat_capacity: 60, class_teacher: '', intakeKey: '', scheme: '',
  });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [teachersDivId, setTeachersDivId] = useState(null);
  const [addDivId, setAddDivId] = useState(null);
  const [addSelected, setAddSelected] = useState([]);
  const [addSearch, setAddSearch] = useState('');
  const [merging, setMerging] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async () => {
    try {
      setLoading(true);
      setError(null);
      const [deptRes, yearRes, semRes, divRes, stuRes, facRes, schemeRes] = await Promise.allSettled([
        academicApi.getDepartments(),
        academicApi.getAcademicYears(),
        academicApi.getSemesters(),
        academicApi.getDivisions(),
        studentApi.getStudents({ page_size: 500 }),
        facultyApi.getFacultyList({ page_size: 500 }),
        curriculumApi.getSchemes({ page_size: 100 }),
      ]);
      const deptList = deptRes.status === 'fulfilled' ? deptRes.value.data?.results || deptRes.value.data || [] : [];
      const yearList = yearRes.status === 'fulfilled' ? yearRes.value.data?.results || yearRes.value.data || [] : [];
      const semList = semRes.status === 'fulfilled' ? semRes.value.data?.results || semRes.value.data || [] : [];
      const divList = divRes.status === 'fulfilled' ? divRes.value.data?.results || divRes.value.data || [] : [];
      const stuList = stuRes.status === 'fulfilled' ? stuRes.value.data?.results || stuRes.value.data || [] : [];
      const facList = facRes.status === 'fulfilled' ? facRes.value.data?.results || facRes.value.data || [] : [];
      const schemeList = schemeRes.status === 'fulfilled' ? schemeRes.value.data?.results || schemeRes.value.data || [] : [];

      let finalDepts = deptList;
      let initialDept = selectedDept;

      if (isHOD && hodDeptId) {
        finalDepts = deptList.filter((d) => String(d.id) === String(hodDeptId));
        initialDept = hodDeptId;
      } else if (isHOD && deptList.length > 0 && !hodDeptId) {
        // Fallback for HOD with CSE default
        const cse = deptList.find((d) => d.code === 'CSE') || deptList[0];
        finalDepts = [cse];
        initialDept = cse.id;
      } else if (!initialDept && deptList.length > 0) {
        initialDept = deptList[0].id;
      }

      setDepartments(finalDepts);
      setSelectedDept(initialDept);
      setYears(yearList);
      setSemesters(semList);
      setDivisions(divList);
      setStudents(stuList);
      setFaculties(facList);
      setSchemes(schemeList);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load divisions & batches.');
    } finally {
      setLoading(false);
    }
  };

  const deptCode = useMemo(() => {
    const d = departments.find((x) => String(x.id) === String(selectedDept));
    return d?.code || '';
  }, [departments, selectedDept]);

  // ---- Pending imports: unconfirmed students grouped by (admission year, stream, sem).
  // This is the HOD-visible "import session" list — derived from enrollments,
  // no ImportBatch permission needed (batches stay admin-only).
  const pendingGroups = useMemo(() => {
    const map = new Map();
    students
      .filter((s) => !s.placement_finalized)
      .filter((s) => (deptCode ? s.department_code === deptCode : true))
      .forEach((s) => {
        const key = `${s.admission_year_code || '—'}__${s.is_direct_second_year ? 'DSE' : 'FY'}__${s.semester_number || '?'}`;
        if (!map.has(key)) {
          map.set(key, {
            key,
            admissionYear: s.admission_year_code || '—',
            stream: s.is_direct_second_year ? 'DSE' : 'FY',
            sem: s.semester_number,
            students: [],
          });
        }
        map.get(key).students.push(s);
      });
    return [...map.values()].sort((a, b) =>
      String(a.admissionYear).localeCompare(String(b.admissionYear)) || Number(a.sem) - Number(b.sem)
    );
  }, [students, deptCode]);

  const deptDivisions = useMemo(() => {
    if (!selectedDept) return divisions;
    return divisions.filter((d) => String(d.department) === String(selectedDept) || String(d.department_id) === String(selectedDept));
  }, [divisions, selectedDept]);

  const rosterOf = (divId) => students.filter((s) => String(s.division_id) === String(divId));

  // Candidates for "Add students": same dept + same sem, not yet confirmed,
  // sitting outside this division (covers later DSE imports merged into an FY class).
  const addCandidates = (div) => {
    const divSem = Number(div.semester_number ?? div.semester);
    return students.filter((s) =>
      !s.placement_finalized &&
      String(s.division_id) !== String(div.id) &&
      Number(s.semester_number) === Number(divSem || s.semester_number) &&
      (deptCode ? s.department_code === deptCode : true)
    );
  };

  const facultyName = (fid) => {
    if (!fid) return '';
    const f = faculties.find((x) => String(x.id) === String(fid) || String(x.user) === String(fid) || String(x.user_id) === String(fid));
    return f?.display_name || f?.name || f?.username || 'Assigned';
  };

  // ---- Create Division (form + intake select, then finalize intake into it)
  const openCreateModal = () => {
    const curYear = years.find((y) => y.is_current) || years[0];
    const firstGroup = pendingGroups[0];
    let semId = '';
    if (firstGroup) {
      const match = semesters.find((s) => Number(s.number) === Number(firstGroup.sem));
      if (match) semId = match.id;
    }
    setCreateForm({
      academic_year: curYear?.id || '',
      semester: semId,
      name: nextDivisionName(curYear?.id || '', semId),
      seat_capacity: 60,
      class_teacher: '',
      intakeKey: firstGroup?.key || '',
    });
    setCreateError('');
    setShowCreateModal(true);
  };

  const nextDivisionName = (yearId, semId) => {
    const used = new Set(
      divisions
        .filter((d) =>
          (!yearId || String(d.academic_year) === String(yearId) || String(d.academic_year_id) === String(yearId)) &&
          (!semId || String(d.semester) === String(semId) || String(d.semester_id) === String(semId))
        )
        .map((d) => String(d.name || '').toUpperCase())
    );
    for (let i = 0; i < 26; i += 1) {
      if (!used.has(divisionLetter(i))) return divisionLetter(i);
    }
    return 'A';
  };

  const handleCreateDivision = async (e) => {
    e.preventDefault();
    setCreateError('');
    if (!selectedDept) {
      setCreateError('No department in scope.');
      return;
    }
    if (!createForm.academic_year || !createForm.semester || !createForm.name.trim()) {
      setCreateError('Academic year, semester and division name are required.');
      return;
    }
    const dupe = divisions.find((d) =>
      (String(d.academic_year) === String(createForm.academic_year) || String(d.academic_year_id) === String(createForm.academic_year)) &&
      (String(d.semester) === String(createForm.semester) || String(d.semester_id) === String(createForm.semester)) &&
      String(d.name || '').toUpperCase() === String(createForm.name.trim()).toUpperCase() &&
      (String(d.department) === String(selectedDept) || String(d.department_id) === String(selectedDept))
    );
    if (dupe) {
      setCreateError(`Division ${createForm.name.trim().toUpperCase()} already exists for this semester — open its card instead.`);
      return;
    }
    setCreating(true);
    try {
      const created = await academicApi.createDivision({
        department: selectedDept,
        academic_year: createForm.academic_year,
        semester: createForm.semester,
        name: createForm.name.trim().toUpperCase(),
        seat_capacity: Number(createForm.seat_capacity) || 60,
        ...(createForm.class_teacher ? { class_teacher: createForm.class_teacher } : {}),
      });
      const newId = created.data?.id;
      const group = pendingGroups.find((g) => g.key === createForm.intakeKey);
      if (group && newId) {
        const res = await academicApi.assignStudents(newId, { student_ids: group.students.map((s) => s.id) });
        setActionMsg(`Division ${createForm.name.trim().toUpperCase()} created — ${res.data?.moved?.length ?? group.students.length} student(s) placed.`);
      } else {
        setActionMsg(`Division ${createForm.name.trim().toUpperCase()} created.`);
      }
      setActionError(null);
      setShowCreateModal(false);
      await loadAll();
    } catch (err) {
      setCreateError(err.response?.data?.detail || 'Failed to create division.');
    } finally {
      setCreating(false);
    }
  };

  // ---- Add students (merge later imports, e.g. DSE, into an existing class)
  const openAddModal = (div) => {
    setAddDivId(div.id);
    setAddSelected([]);
    setAddSearch('');
    setShowAddModal(true);
  };

  const handleMergeStudents = async () => {
    if (!addDivId || addSelected.length === 0) return;
    if (!window.confirm(`Place ${addSelected.length} student(s) into this class?`)) return;
    setMerging(true);
    try {
      const res = await academicApi.assignStudents(addDivId, { student_ids: addSelected });
      const skipped = res.data?.skipped?.length || 0;
      setActionMsg(`${res.data?.detail || 'Students placed.'}${skipped ? ` ${skipped} skipped.` : ''}`);
      setActionError(null);
      setShowAddModal(false);
      setAddDivId(null);
      setAddSelected([]);
      await loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to add students.');
    } finally {
      setMerging(false);
    }
  };

  // ---- Move one student to another class (same single-student endpoint)
  const handleMoveStudent = async (studentId, divisionId) => {
    if (!divisionId) return;
    try {
      setActionMsg(null);
      setActionError(null);
      await studentApi.assignDivision(studentId, { division_id: divisionId });
      const divObj = divisions.find((d) => String(d.id) === String(divisionId));
      setStudents((prev) =>
        prev.map((s) => (String(s.id) === String(studentId)
          ? { ...s, division_id: divisionId, division_name: divObj ? divObj.name : s.division_name, placement_finalized: true }
          : s))
      );
      setActionMsg('Student moved to the selected class.');
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to move student.');
    }
  };

  // ---- Delete an empty class (backend also blocks non-empty)
  const handleDeleteDivision = async (div) => {
    const rosterCount = rosterOf(div.id).length;
    if (rosterCount > 0) return;
    if (!window.confirm(`Delete empty Division ${div.name} (Sem ${div.semester_number ?? ''})? This is recorded in the audit trail.`)) return;
    try {
      setActionMsg(null);
      setActionError(null);
      await academicApi.deleteDivision(div.id);
      setActionMsg(`Division ${div.name} deleted.`);
      await loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to delete division.');
    }
  };

  // ---- Class teacher change on a card
  const handleSetClassTeacher = async (div, teacherId) => {
    try {
      setActionMsg(null);
      setActionError(null);
      await academicApi.updateDivision(div.id, { class_teacher: teacherId || null });
      setActionMsg('Class teacher updated.');
      await loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to update class teacher.');
    }
  };

  // ---- Expand card: roster is local; subjects + holders load lazily (same APIs as dashboard)
  const ensureDivDetail = async (divId) => {
    if (divDetail[divId]) return;
    setLoadingDetail(true);
    try {
      const [subRes, asgRes] = await Promise.all([
        academicApi.getDivisionSubjects(divId),
        facultyApi.getAssignments({ division_id: divId, is_active: true }),
      ]);
      setDivDetail((prev) => ({
        ...prev,
        [divId]: {
          subjects: subRes.data?.subjects || [],
          assignments: asgRes.data?.results || asgRes.data || [],
          scheme: subRes.data?.scheme || null,
        },
      }));
    } catch {
      setDivDetail((prev) => ({ ...prev, [divId]: { subjects: [], assignments: [], scheme: null } }));
    } finally {
      setLoadingDetail(false);
    }
  };

  const toggleExpand = async (div) => {
    if (String(expandedDivId) === String(div.id)) {
      setExpandedDivId(null);
      return;
    }
    setExpandedDivId(div.id);
    await ensureDivDetail(div.id);
  };

  // Subject-teacher table lives in its own popup (opened by Set button);
  // class-teacher setting lives there too as the first row.
  const openTeachersModal = async (div) => {
    setTeachersDivId(div.id);
    await ensureDivDetail(div.id);
  };

  const holderOf = (divId, subject) => {
    const list = divDetail[divId]?.assignments || [];
    return list.find((a) => a.scheme_subject === subject.id && a.role !== 'LAB_INSTRUCTOR' && a.is_active)
      || list.find((a) => (a.subject_code || '').toUpperCase() === (subject.course_code || '').toUpperCase() && a.role !== 'LAB_INSTRUCTOR' && a.is_active && !a.scheme_subject)
      || null;
  };

  const handleSaveSlot = async (divId, subject, facultyIdOverride) => {
    const facultyId = facultyIdOverride ?? slotEdit[subject.id];
    if (!facultyId) return;
    const holder = holderOf(divId, subject);
    if (holder && String(holder.faculty) === String(facultyId)) {
      setSlotEdit((prev) => {
        const next = { ...prev };
        delete next[subject.id];
        return next;
      });
      return;
    }
    setSavingSlot(subject.id);
    try {
      if (holder) {
        await facultyApi.deactivateAssignment(holder.id, 'HOD replaced subject teacher');
      }
      await facultyApi.createAssignment({
        faculty: facultyId,
        division: divId,
        scheme_subject: subject.id,
        role: 'PRIMARY_FACULTY',
      });
      setActionMsg(`${subject.course_code} teacher saved.`);
      setActionError(null);
      setSlotEdit((prev) => {
        const next = { ...prev };
        delete next[subject.id];
        return next;
      });
      const [subRes, asgRes] = await Promise.all([
        academicApi.getDivisionSubjects(divId),
        facultyApi.getAssignments({ division_id: divId, is_active: true }),
      ]);
      setDivDetail((prev) => ({
        ...prev,
        [divId]: {
          subjects: subRes.data?.subjects || [],
          assignments: asgRes.data?.results || asgRes.data || [],
          scheme: subRes.data?.scheme || null,
        },
      }));
    } catch (err) {
      const data = err.response?.data;
      setActionError(data?.detail || (data && typeof data === 'object' ? Object.values(data).flat().join(' ') : null) || 'Failed to save teacher.');
    } finally {
      setSavingSlot(null);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '2rem' }}>
        <LoadingState message="Loading divisions & batches..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '2rem' }}>
        <ErrorState title="Failed to load" message={error} onRetry={loadAll} />
      </div>
    );
  }

  const addModalDiv = divisions.find((d) => String(d.id) === String(addDivId)) || null;
  const addModalCandidates = addModalDiv
    ? addCandidates(addModalDiv).filter((s) =>
        !addSearch.trim() ||
        `${s.display_name || ''} ${s.enrollment_no || ''} ${s.application_id || ''}`.toLowerCase().includes(addSearch.trim().toLowerCase())
      )
    : [];

  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: 'Home', to: '/dashboard' }, { label: 'Classes & Divisions' }]}
        title="Classes & Divisions"
        subtitle="Create divisions for imported student batches and view all existing classes in your department."
      />
      <div className="edvana-banner-overlap">
        {(actionMsg || actionError) && (
          <div
            style={{
              marginBottom: '1rem',
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.875rem',
              backgroundColor: actionError ? '#fef2f2' : '#f0fdf4',
              border: `1px solid ${actionError ? '#fecaca' : '#bbf7d0'}`,
              color: actionError ? '#dc2626' : '#16a34a',
            }}
          >
            {actionError || actionMsg}
          </div>
        )}

        {/* Pending-imports notification: unconfirmed students grouped by intake */}
        {pendingGroups.length > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.9rem 1.25rem',
              background: '#eff6ff',
              border: '1px solid #bfdbfe',
              borderRadius: '10px',
              marginBottom: '1rem',
              fontSize: '0.85rem',
              color: '#1e40af',
            }}
          >
            <Bell size={18} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1 }}>
              <strong>{pendingGroups.reduce((n, g) => n + g.students.length, 0)} new imports pending division creation</strong>
              <span style={{ color: '#3b82f6' }}> — Administrative Head has imported new student data. Please create divisions to assign students.</span>
            </span>
            <button
              type="button"
              onClick={() => document.getElementById('hod-pending-imports')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
              className="edvana-btn edvana-btn-secondary"
              style={{ whiteSpace: 'nowrap' }}
            >
              View Imports →
            </button>
          </div>
        )}

        {/* Imports pending division creation */}
        <div id="hod-pending-imports" className="edvana-card" style={{ padding: '1.5rem 1.75rem', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Imports Pending Division Creation</h3>
              <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: '#64748b' }}>
                Imported batches whose students are not placed in a class yet. Create a division to place them.
              </p>
            </div>
            {canManage && pendingGroups.length > 0 && (
              <button type="button" className="edvana-btn edvana-btn-primary" onClick={openCreateModal}>
                <Plus size={14} /> Create Division
              </button>
            )}
          </div>
          {pendingGroups.length === 0 ? (
            <div style={{ padding: '1.25rem', textAlign: 'center', color: '#64748b', fontSize: '0.875rem' }}>
              No pending imports — every imported student is placed in a class.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="edvana-table" style={{ margin: 0 }}>
                <thead>
                  <tr>
                    <th>Academic Year</th>
                    <th>Program / Stream</th>
                    <th>Year - Sem</th>
                    <th style={{ textAlign: 'center' }}>Total Students</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingGroups.map((g) => (
                    <tr key={g.key}>
                      <td style={{ fontWeight: 700 }}>{g.admissionYear}</td>
                      <td>
                        {deptCode} ({g.stream === 'DSE' ? 'DSY Lateral' : 'Regular'})
                      </td>
                      <td>{semLabel(semesters, g.sem)}</td>
                      <td style={{ textAlign: 'center', fontWeight: 700 }}>{g.students.length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Existing classes & divisions */}
        <div className="edvana-card" style={{ padding: '1.5rem 1.75rem', marginBottom: '1.25rem' }}>
          <div style={{ marginBottom: '1rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Existing Classes & Divisions</h3>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.8125rem', color: '#64748b' }}>
              Click a class to see students and subject teachers. Late imports (e.g. DSE) can be merged into a class with Add students.
            </p>
          </div>
          {deptDivisions.length === 0 ? (
            <div style={{ padding: '1.25rem', textAlign: 'center', color: '#64748b', fontSize: '0.875rem' }}>
              No classes yet — create the first division from a pending import above.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {deptDivisions.map((d) => {
                const roster = rosterOf(d.id);
                const strength = d.enrolled_count ?? roster.length;
                const semNo = d.semester_number ?? d.semester;
                const isOpen = String(expandedDivId) === String(d.id);
                const detail = divDetail[d.id];
                const mergeable = addCandidates(d);
                return (
                  <div key={d.id} style={{ border: '1px solid #e2e8f0', borderRadius: '18px', background: '#ffffff', boxShadow: '0 1px 3px rgba(15, 23, 42, 0.05)' }}>
                    <button
                      type="button"
                      onClick={() => toggleExpand(d)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: '0.75rem',
                        padding: '0.9rem 1.1rem', background: 'transparent', border: 'none',
                        cursor: 'pointer', textAlign: 'left', flexWrap: 'wrap',
                      }}
                    >
                      <span style={{ color: '#64748b', display: 'inline-flex' }}>
                        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      </span>
                      <span style={{ fontWeight: 700, color: '#0f172a' }}>
                        {d.academic_year_code || years.find((y) => String(y.id) === String(d.academic_year || d.academic_year_id))?.code || '—'}
                      </span>
                      <span style={{ fontSize: '0.8125rem', color: '#475569' }}>{semLabel(semesters, semNo)}</span>
                      <span
                        style={{
                          fontSize: '0.75rem', fontWeight: 700, background: '#1E60DC', color: '#fff',
                          borderRadius: '6px', padding: '0.2rem 0.55rem',
                        }}
                      >
                        Div {d.name}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace' }}>{d.class_code || ''}</span>
                      <span style={{ fontSize: '0.8125rem', color: d.class_teacher_name ? '#0f172a' : '#b45309', fontWeight: 600 }}>
                        {d.class_teacher_name ? `👩‍🏫 ${d.class_teacher_name}` : 'No class teacher'}
                      </span>
                      <span style={{ marginLeft: 'auto', fontSize: '0.8125rem', color: '#475569', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                        <Users size={14} /> {strength}
                      </span>
                    </button>

                    {isOpen && (
                      <div style={{ borderTop: '1px solid #f1f5f9', padding: '1rem 1.2rem 1.2rem' }} onClick={(e) => e.stopPropagation()}>
                        {(mergeable.length > 0 || (roster.length === 0 && canManage)) && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                            {mergeable.length > 0 && (
                              <button
                                type="button"
                                className="edvana-btn edvana-btn-secondary"
                                onClick={() => openAddModal(d)}
                              >
                                <Plus size={13} /> Add students ({mergeable.length})
                              </button>
                            )}
                            {roster.length === 0 && canManage && (
                              <button
                                type="button"
                                onClick={() => handleDeleteDivision(d)}
                                style={{
                                  background: '#fff', border: '1px solid #fecaca', borderRadius: '8px',
                                  padding: '0.35rem 0.7rem', fontSize: '0.75rem', fontWeight: 600,
                                  color: '#b91c1c', cursor: 'pointer',
                                }}
                              >
                                Delete empty class
                              </button>
                            )}
                          </div>
                        )}

                        {/* Subject teachers — set inside the popup table */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.9rem', flexWrap: 'wrap', background: '#f8fafc', border: '1px solid #e8eef6', borderRadius: '12px', padding: '0.6rem 0.85rem' }}>
                          <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#0f172a', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                            <BookOpen size={14} /> Subject Teachers
                          </span>
                          {detail && detail.subjects.length > 0 && (
                            <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                              {detail.assignments.filter((a) => a.is_active && a.role !== 'LAB_INSTRUCTOR').length}/{detail.subjects.length} set
                              {d.class_teacher_name ? ` • Class teacher: ${d.class_teacher_name}` : ' • No class teacher'}
                            </span>
                          )}
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-secondary"
                            onClick={() => openTeachersModal(d)}
                            style={{ marginLeft: 'auto', height: '32px', fontSize: '0.78rem', borderRadius: '16px' }}
                          >
                            Set Subject Teachers
                          </button>
                        </div>
                        {loadingDetail && !detail && (
                          <div style={{ fontSize: '0.8125rem', color: '#64748b', marginBottom: '0.5rem' }}>Loading subjects…</div>
                        )}

                        {/* Students in this class */}
                        <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>
                          Students ({roster.length})
                        </div>
                        {roster.length === 0 ? (
                          <div style={{ fontSize: '0.8125rem', color: '#64748b', marginBottom: '0.75rem' }}>No students placed yet.</div>
                        ) : (
                          <div style={{ overflowX: 'auto', marginBottom: '0.75rem', border: '1px solid #e8eef6', borderRadius: '14px' }}>
                            <table className="edvana-table" style={{ margin: 0, fontSize: '0.8rem' }}>
                              <thead>
                                <tr>
                                  <th>Name</th>
                                  <th>Enrollment No</th>
                                  <th style={{ textAlign: 'center' }}>Stream</th>
                                  <th style={{ textAlign: 'center' }}>Move</th>
                                </tr>
                              </thead>
                              <tbody>
                                {roster.map((s) => (
                                  <tr key={s.id}>
                                    <td style={{ fontWeight: 600 }}>{s.display_name}</td>
                                    <td style={{ fontFamily: 'monospace', fontSize: '0.76rem' }}>{s.enrollment_no || s.application_id}</td>
                                    <td style={{ textAlign: 'center' }}>{s.is_direct_second_year ? 'DSY' : 'Regular'}</td>
                                    <td style={{ textAlign: 'center' }}>
                                      <select
                                        className="edvana-input"
                                        value={s.division_id || ''}
                                        onChange={(e) => { if (e.target.value && String(e.target.value) !== String(d.id)) handleMoveStudent(s.id, e.target.value); }}
                                        style={{ height: '30px', fontSize: '0.75rem', minWidth: '110px' }}
                                        title="Move student to another class"
                                      >
                                        {deptDivisions
                                          .filter((x) => Number(x.semester_number ?? x.semester) === Number(d.semester_number ?? d.semester))
                                          .map((x) => (
                                            <option key={x.id} value={x.id}>
                                              Div {x.name}{String(x.id) === String(d.id) ? ' (here)' : ''}
                                            </option>
                                          ))}
                                      </select>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}

                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="edvana-card" style={{ padding: '0.9rem 1.25rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, fontSize: '0.875rem' }}>Department:</span>
          {isHOD ? (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.45rem 0.85rem',
                backgroundColor: '#eff6ff',
                borderRadius: '6px',
                border: '1px solid #bfdbfe',
                fontWeight: 600,
                color: '#1e40af',
                fontSize: '0.85rem',
              }}
            >
              <span>{departments[0]?.name || 'Department'} ({departments[0]?.code || 'CSE'})</span>
              <span
                style={{
                  fontSize: '0.72rem',
                  background: '#dbeafe',
                  color: '#1e3a8a',
                  padding: '0.1rem 0.45rem',
                  borderRadius: '4px',
                  fontWeight: 700,
                }}
              >
                Locked to HOD Scope
              </span>
            </span>
          ) : (
            <select className="edvana-input" value={selectedDept} onChange={(e) => setSelectedDept(e.target.value)} style={{ minWidth: '220px' }}>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.code})
                </option>
              ))}
            </select>
          )}
          <span style={{ fontSize: '0.8125rem', color: '#64748b', marginLeft: 'auto' }}>
            {deptDivisions.length} classes • {students.length} students
          </span>
        </div>
      </div>

      {/* Subject teachers popup: class teacher + one row per scheme subject */}
      {teachersDivId && (() => {
        const div = divisions.find((x) => String(x.id) === String(teachersDivId));
        if (!div) return null;
        const detail = divDetail[div.id];
        const ctKey = `ct-${div.id}`;
        const ctEditing = slotEdit[ctKey] !== undefined;
        return (
          <Modal
            isOpen
            onClose={() => setTeachersDivId(null)}
            title={`Subject Teachers — Div ${div.name} (Sem ${div.semester_number ?? ''})`}
            maxWidth="640px"
          >
            <div style={{ padding: '0.25rem 0' }}>
              {loadingDetail && !detail ? (
                <div style={{ padding: '1.5rem', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>Loading subjects…</div>
              ) : (
                <>
                <div style={{ overflowX: 'auto', border: '1px solid #e8eef6', borderRadius: '14px' }}>
                  <table className="edvana-table" style={{ margin: 0, fontSize: '0.82rem' }}>
                    <thead>
                      <tr>
                        <th>Subject</th>
                        <th style={{ width: '250px' }}>Teacher</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ background: '#f8fafc' }}>
                        <td style={{ fontWeight: 700 }}>Class Teacher <span style={{ color: '#64748b', fontWeight: 500 }}>(overall)</span></td>
                        <td>
                          <TeacherCell
                            holderLabel={div.class_teacher_name || ''}
                            editing={ctEditing}
                            value={slotEdit[ctKey] || ''}
                            faculties={faculties}
                            saving={false}
                            placeholder={div.class_teacher_name ? 'Change teacher…' : 'Assign teacher…'}
                            onEdit={() => setSlotEdit((prev) => ({ ...prev, [ctKey]: '' }))}
                            onPick={async (fid) => {
                              await handleSetClassTeacher(div, fid);
                              setSlotEdit((prev) => {
                                const next = { ...prev };
                                delete next[ctKey];
                                return next;
                              });
                            }}
                          />
                        </td>
                      </tr>
                      {(detail?.subjects || []).map((sub) => {
                        const holder = holderOf(div.id, sub);
                        const editing = slotEdit[sub.id] !== undefined;
                        return (
                          <tr key={sub.id}>
                            <td>
                              <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>{sub.course_code}</span>
                              <span style={{ color: '#64748b' }}> — {sub.subject_title || sub.subject_name || ''}</span>
                            </td>
                            <td>
                              <TeacherCell
                                holderLabel={holder ? facultyName(holder.faculty) : ''}
                                editing={editing}
                                value={slotEdit[sub.id] || ''}
                                faculties={faculties}
                                saving={savingSlot === sub.id}
                                placeholder="Assign teacher…"
                                onEdit={() => setSlotEdit((prev) => ({ ...prev, [sub.id]: String(holder.faculty || '') }))}
                                onPick={(fid) => handleSaveSlot(div.id, sub, fid)}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {(!detail || detail.subjects.length === 0) && (
                  <div style={{ marginTop: '0.9rem', border: '1px dashed #cbd5e1', borderRadius: '12px', padding: '0.85rem 1rem', background: '#f8fafc' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem' }}>
                      <span style={{ fontSize: '0.68rem', fontWeight: 800, background: '#e2e8f0', color: '#475569', borderRadius: '4px', padding: '0.1rem 0.4rem', letterSpacing: '0.04em' }}>
                        SAMPLE PREVIEW
                      </span>
                      <span style={{ fontSize: '0.76rem', color: '#64748b' }}>
                        No scheme subjects published yet — subject rows will look like this:
                      </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.8rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', background: '#fff', border: '1px solid #e8eef6', borderRadius: '10px', padding: '0.5rem 0.75rem' }}>
                        <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>CS101</span>
                        <span style={{ color: '#64748b' }}>— Engineering Mathematics I</span>
                        <span style={{ marginLeft: 'auto' }}>
                          <span
                            style={{
                              display: 'inline-flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem',
                              fontSize: '0.78rem', color: '#94a3b8', border: '1px solid #e2e8f0', borderRadius: '6px',
                              padding: '0.3rem 0.6rem', minWidth: '190px', background: '#fff',
                            }}
                          >
                            Assign teacher… <span style={{ fontSize: '0.65rem' }}>▾</span>
                          </span>
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', background: '#fff', border: '1px solid #e8eef6', borderRadius: '10px', padding: '0.5rem 0.75rem' }}>
                        <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>CS102</span>
                        <span style={{ color: '#64748b' }}>— Engineering Physics</span>
                        <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
                          <span
                            style={{
                              display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                              background: '#f0fdf4', color: '#15803d', border: '1px solid #bbf7d0',
                              borderRadius: '9999px', padding: '0.2rem 0.65rem',
                              fontSize: '0.75rem', fontWeight: 700,
                            }}
                          >
                            <Check size={12} /> {faculties[0]?.display_name || 'Prof. Priya Deshmukh'}
                          </span>
                          <span
                            style={{
                              background: '#fff', border: '1px solid #e2e8f0', borderRadius: '6px',
                              padding: '0.25rem', display: 'inline-flex', color: '#475569',
                            }}
                          >
                            <Pencil size={13} />
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                </>
              )}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                <button type="button" className="edvana-btn edvana-btn-secondary" onClick={() => setTeachersDivId(null)}>
                  Done
                </button>
              </div>
            </div>
          </Modal>
        );
      })()}

      {/* Create Class / Division modal (display aids: Scheme/Year/Class-Code
          are derived, never persisted — only dept/year/sem/name/strength/
          teacher reach the backend) */}
      {showCreateModal && (() => {
        const cSem = semesters.find((s) => String(s.id) === String(createForm.semester));
        const cYearName = YEAR_NAMES[Number(cSem?.year_level)] || '';
        const cYearCode = years.find((y) => String(y.id) === String(createForm.academic_year))?.code || '';
        const cSemNo = cSem?.number;
        const cTerm = (cSem?.term_type || '').toUpperCase() === 'EVEN' ? 'Even' : 'Odd';
        const cCode = (cSemNo && createForm.name.trim())
          ? `${deptCode || 'DEPT'}-Sem${cSemNo}-${createForm.name.trim().toUpperCase()}`
          : '';
        const cIntake = pendingGroups.find((g) => g.key === createForm.intakeKey);
        const req = <span style={{ color: '#dc2626' }}> *</span>;
        const inputStyle = { width: '100%', height: '42px', marginTop: '0.3rem', borderRadius: '10px' };
        const labelStyle = { fontSize: '0.8rem', fontWeight: 600, color: '#0f172a' };
        return (
          <Modal
            isOpen={showCreateModal}
            onClose={() => setShowCreateModal(false)}
            title={(
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.05rem', fontWeight: 800, color: '#0f172a' }}>
                  <Users size={19} style={{ color: '#1E60DC' }} />
                  <span>Create Class / Division</span>
                </div>
                <div style={{ fontSize: '0.8rem', fontWeight: 400, color: '#64748b', marginTop: '0.15rem' }}>
                  Create a new class and division for your department
                </div>
              </div>
            )}
            maxWidth="600px"
            style={{ borderRadius: '20px' }}
          >
            <form onSubmit={handleCreateDivision} style={{ padding: '0.25rem 0 0' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem 1rem', marginBottom: '0.9rem' }}>
                <div>
                  <label style={labelStyle}>Academic Year{req}</label>
                  <select
                    className="edvana-input"
                    value={createForm.academic_year}
                    onChange={(e) => {
                      const v = e.target.value;
                      setCreateForm((p) => ({ ...p, academic_year: v, name: nextDivisionName(v, p.semester) }));
                    }}
                    style={inputStyle}
                  >
                    <option value="">Select year…</option>
                    {years.map((y) => (
                      <option key={y.id} value={y.id}>{y.code}{y.is_current ? ' (Active)' : ''}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle} title="Display aid only — students keep their entry scheme">
                    Scheme <span style={{ color: '#94a3b8', cursor: 'help' }}>ⓘ</span>
                  </label>
                  <select
                    className="edvana-input"
                    value={createForm.scheme}
                    onChange={(e) => setCreateForm((p) => ({ ...p, scheme: e.target.value }))}
                    style={inputStyle}
                    title="Display aid only — students keep their entry scheme"
                  >
                    <option value="">Auto (entry scheme)</option>
                    {schemes.map((s) => (
                      <option key={s.id} value={s.id}>{s.code || s.name}{s.version ? ` (${s.version})` : ''}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Year{req}</label>
                  <input className="edvana-input" readOnly disabled value={cYearName || ''} placeholder="Follows semester" style={{ ...inputStyle, background: '#f8fafc' }} />
                </div>
                <div>
                  <label style={labelStyle} title="Odd/even term of the semester">Semester{req} <span style={{ color: '#94a3b8', cursor: 'help' }}>ⓘ</span></label>
                  <select
                    className="edvana-input"
                    value={createForm.semester}
                    onChange={(e) => {
                      const v = e.target.value;
                      setCreateForm((p) => ({ ...p, semester: v, name: nextDivisionName(p.academic_year, v) }));
                    }}
                    style={inputStyle}
                  >
                    <option value="">Select sem…</option>
                    {semesters.map((s) => (
                      <option key={s.id} value={s.id}>Sem {s.number} ({(s.term_type || '').toUpperCase() === 'EVEN' ? 'Even' : 'Odd'})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Division{req}</label>
                  <input
                    className="edvana-input"
                    value={createForm.name}
                    onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value.toUpperCase().slice(0, 2) }))}
                    placeholder="e.g. A, B, C"
                    style={inputStyle}
                  />
                </div>
                <div>
                  <label style={labelStyle}>Class Code <span style={{ fontWeight: 400, color: '#64748b' }}>(Optional)</span></label>
                  <input className="edvana-input" readOnly disabled value={cCode} placeholder="Auto-generated if left blank" style={{ ...inputStyle, background: '#f8fafc', fontFamily: 'monospace' }} />
                </div>
                <div>
                  <label style={labelStyle}>Class Teacher</label>
                  <select
                    className="edvana-input"
                    value={createForm.class_teacher}
                    onChange={(e) => setCreateForm((p) => ({ ...p, class_teacher: e.target.value }))}
                    style={inputStyle}
                  >
                    <option value="">— Assign later —</option>
                    {faculties.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.display_name || f.name || f.username || f.employee_code}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Expected Strength <span style={{ fontWeight: 400, color: '#64748b' }}>(Optional)</span></label>
                  <input
                    type="number"
                    className="edvana-input"
                    value={createForm.seat_capacity}
                    onChange={(e) => setCreateForm((p) => ({ ...p, seat_capacity: e.target.value }))}
                    style={inputStyle}
                  />
                </div>
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <label style={labelStyle}>Import to place <span style={{ fontWeight: 400, color: '#64748b' }}>(latest first)</span></label>
                <select
                  className="edvana-input"
                  value={createForm.intakeKey}
                  onChange={(e) => setCreateForm((p) => ({ ...p, intakeKey: e.target.value }))}
                  style={inputStyle}
                >
                  <option value="">— Create empty, place later —</option>
                  {pendingGroups.map((g) => (
                    <option key={g.key} value={g.key}>
                      {g.admissionYear} • {g.stream === 'DSE' ? 'DSY' : 'Regular'} • Sem {g.sem} • {g.students.length} students
                    </option>
                  ))}
                </select>
              </div>
              {(cYearName || cSemNo || createForm.name.trim() || cYearCode) && (
                <div style={{ display: 'flex', gap: '0.6rem', background: '#eff6ff', border: '1px solid #dbeafe', borderRadius: '12px', padding: '0.8rem 1rem', marginBottom: '1rem', fontSize: '0.8rem', color: '#1e40af', lineHeight: 1.55 }}>
                  <span style={{ flexShrink: 0, fontWeight: 800 }}>ⓘ</span>
                  <span>
                    <strong>This will create:</strong><br />
                    {cYearName || '—'} – Semester {cSemNo || '—'} ({cTerm}) – Division {createForm.name.trim().toUpperCase() || '—'} for Academic Year {cYearCode || '—'}
                    {cCode ? ` (${cCode})` : ''}. Students can be assigned to this class after creation.
                    {cIntake ? ` ${cIntake.students.length} student(s) from the selected import will be placed.` : ''}
                  </span>
                </div>
              )}
              {createError && (
                <div style={{ marginBottom: '1rem', padding: '0.6rem 0.85rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '10px', fontSize: '0.8125rem', color: '#991b1b' }}>
                  {createError}
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', paddingTop: '0.25rem' }}>
                <button
                  type="button"
                  className="edvana-btn edvana-btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  style={{ borderRadius: '10px', padding: '0.55rem 1.25rem' }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="edvana-btn edvana-btn-primary"
                  style={{ borderRadius: '10px', padding: '0.55rem 1.25rem' }}
                >
                  {creating ? 'Creating…' : 'Create Class / Division'}
                </button>
              </div>
            </form>
          </Modal>
        );
      })()}

      {/* Add students modal: merge a later import (e.g. DSE) into this class */}
      {showAddModal && addModalDiv && (
        <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title={`Add students — Div ${addModalDiv.name}`} maxWidth="620px">
          <div style={{ padding: '0.5rem 0' }}>
            <div style={{ position: 'relative', marginBottom: '0.75rem' }}>
              <Search size={15} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                className="edvana-input"
                placeholder="Search name, enrollment no…"
                value={addSearch}
                onChange={(e) => setAddSearch(e.target.value)}
                style={{ width: '100%', paddingLeft: '32px', height: '38px' }}
              />
            </div>
            <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.5rem' }}>
              Unplaced {deptCode} Sem {addModalDiv.semester_number ?? ''} students — tick to merge into this class.
            </div>
            <div style={{ maxHeight: '320px', overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '8px' }}>
              {addModalCandidates.length === 0 ? (
                <div style={{ padding: '1.5rem', textAlign: 'center', color: '#64748b', fontSize: '0.85rem' }}>No unplaced students for this semester.</div>
              ) : (
                <table className="edvana-table" style={{ margin: 0, fontSize: '0.8rem' }}>
                  <thead>
                    <tr>
                      <th style={{ width: '36px' }}>
                        <input
                          type="checkbox"
                          checked={addModalCandidates.length > 0 && addSelected.length === addModalCandidates.length}
                          onChange={(e) => setAddSelected(e.target.checked ? addModalCandidates.map((s) => s.id) : [])}
                        />
                      </th>
                      <th>Name</th>
                      <th>Enrollment No</th>
                      <th style={{ textAlign: 'center' }}>Stream</th>
                    </tr>
                  </thead>
                  <tbody>
                    {addModalCandidates.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={addSelected.includes(s.id)}
                            onChange={() => setAddSelected((prev) => (prev.includes(s.id) ? prev.filter((x) => x !== s.id) : [...prev, s.id]))}
                          />
                        </td>
                        <td style={{ fontWeight: 600 }}>{s.display_name}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.76rem' }}>{s.enrollment_no || s.application_id}</td>
                        <td style={{ textAlign: 'center' }}>{s.is_direct_second_year ? 'DSY' : 'Regular'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem', borderTop: '1px solid #f1f5f9', paddingTop: '1rem' }}>
              <button type="button" className="edvana-btn edvana-btn-secondary" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button type="button" className="edvana-btn edvana-btn-primary" disabled={merging || addSelected.length === 0} onClick={handleMergeStudents}>
                {merging ? 'Placing…' : `Confirm (${addSelected.length})`}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
