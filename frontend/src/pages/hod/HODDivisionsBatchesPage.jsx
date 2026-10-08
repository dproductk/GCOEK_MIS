import { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../../context/AuthContext';
import academicApi from '../../api/academicApi';
import admissionsApi from '../../api/admissionsApi';
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
  Trash2,
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

function extractErrorMessage(err, fallback = 'An error occurred.') {
  if (!err) return fallback;
  const data = err.response?.data;
  if (!data) return err.message || fallback;
  if (typeof data === 'string') return data;
  if (data.detail && typeof data.detail === 'string') return data.detail;
  if (typeof data === 'object') {
    const messages = [];
    for (const [key, val] of Object.entries(data)) {
      const valStr = Array.isArray(val) ? val.join(' ') : String(val);
      if (key === 'non_field_errors' || key === 'detail') {
        messages.push(valStr);
      } else {
        const fieldName = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        messages.push(`${fieldName}: ${valStr}`);
      }
    }
    if (messages.length > 0) return messages.join(' | ');
  }
  return fallback;
}

// One teacher cell used by every row of the teachers popup: assigned shows
// just "✓ name" + pencil; unassigned (or editing) shows the faculty dropdown
// directly and saves on pick — no intermediate Set button.
function TeacherCell({
  holderLabel,
  editing,
  value,
  faculties,
  saving,
  placeholder,
  currentSubjectCode,
  assignedHolders = [],
  onEdit,
  onCancelEdit,
  onPick,
}) {
  const busyTeacherMap = useMemo(() => {
    const map = new Map();
    for (const a of (assignedHolders || [])) {
      if (
        a.is_active &&
        a.role !== 'LAB_INSTRUCTOR' &&
        currentSubjectCode &&
        (a.subject_code || '').toUpperCase() !== currentSubjectCode.toUpperCase()
      ) {
        map.set(String(a.faculty), a.subject_code);
      }
    }
    return map;
  }, [assignedHolders, currentSubjectCode]);

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
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem' }}>
      <select
        className="edvana-select"
        value={value || ''}
        disabled={!!saving}
        onChange={(e) => onPick(e.target.value)}
        style={{
          height: '32px',
          fontSize: '0.78rem',
          minWidth: '200px',
          borderColor: saving ? '#3b82f6' : undefined,
        }}
        title={placeholder}
      >
        <option value="">
          {saving ? 'Saving…' : (holderLabel ? '— Unassign teacher —' : placeholder)}
        </option>
        {faculties.map((f) => {
          const busySubject = busyTeacherMap.get(String(f.id));
          return (
            <option key={f.id} value={f.id} disabled={!!busySubject}>
              {f.display_name || f.name || f.username || f.employee_code}
              {busySubject ? ` (teaching ${busySubject})` : ''}
            </option>
          );
        })}
      </select>
      {editing && onCancelEdit && !saving && (
        <button
          type="button"
          onClick={onCancelEdit}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            fontSize: '0.75rem',
            textDecoration: 'underline',
            padding: '0 0.25rem',
          }}
        >
          Cancel
        </button>
      )}
    </div>
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
  const [intakes, setIntakes] = useState(null); // null = not loaded / forbidden -> fallback grouping
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
  const [slotError, setSlotError] = useState(null); // popup-level save error (page banner hides behind modal)
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
  // Place a pending batch slice into an EXISTING class (no new division).
  const [placeTargetKey, setPlaceTargetKey] = useState(null);
  const [placeDivId, setPlaceDivId] = useState('');
  const [placing, setPlacing] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async (showLoading = true) => {
    try {
      if (showLoading) setLoading(true);
      setError(null);
      const [deptRes, yearRes, semRes, divRes, stuRes, facRes, schemeRes, intakeRes] = await Promise.allSettled([
        academicApi.getDepartments(),
        academicApi.getAcademicYears(),
        academicApi.getSemesters(),
        academicApi.getDivisions(),
        studentApi.getStudents({ page_size: 500 }),
        facultyApi.getFacultyList({ page_size: 500 }),
        curriculumApi.getSchemes({ page_size: 100 }),
        admissionsApi.getPendingIntakes(),
      ]);
      const deptList = deptRes.status === 'fulfilled' ? deptRes.value.data?.results || deptRes.value.data || [] : [];
      const yearList = yearRes.status === 'fulfilled' ? yearRes.value.data?.results || yearRes.value.data || [] : [];
      const semList = semRes.status === 'fulfilled' ? semRes.value.data?.results || semRes.value.data || [] : [];
      const divList = divRes.status === 'fulfilled' ? divRes.value.data?.results || divRes.value.data || [] : [];
      const stuList = stuRes.status === 'fulfilled' ? stuRes.value.data?.results || stuRes.value.data || [] : [];
      const facList = facRes.status === 'fulfilled' ? facRes.value.data?.results || facRes.value.data || [] : [];
      const schemeList = schemeRes.status === 'fulfilled' ? schemeRes.value.data?.results || schemeRes.value.data || [] : [];
      const intakeList = intakeRes.status === 'fulfilled' ? (intakeRes.value.data?.results || intakeRes.value.data || []) : null;

      let finalDepts = deptList;
      let initialDept = selectedDept;

      if (isHOD && hodDeptId) {
        finalDepts = deptList.filter((d) => String(d.id) === String(hodDeptId));
        initialDept = hodDeptId;
      } else if (isHOD && deptList.length > 0 && !hodDeptId) {
        // HOD without a mapped department: scope to nothing rather than
        // silently showing another department's data. Sysadmin must map
        // the HOD's department via role assignment.
        finalDepts = [];
        initialDept = '';
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
      setIntakes(Array.isArray(intakeList) ? intakeList : null);
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

  // ---- Pending imports: true single-use batch cards from /pending-intakes/.
  // Each card is one (file batch x dept x stream x sem) slice with its own
  // pending count. A card disappears once pending hits 0, so a batch slice
  // can never be reused. Falls back to the legacy derived grouping when the
  // endpoint is unavailable (seeds without ImportRow links, tests).
  const pendingGroups = useMemo(() => {
    if (Array.isArray(intakes)) {
      const byId = new Map(students.map((s) => [String(s.id), s]));
      return intakes
        .filter((t) => (deptCode ? String(t.department_code) === String(deptCode) : true))
        .filter((t) => (t.pending || 0) > 0)
        .map((t) => {
          const pendingStudents = (t.pending_student_ids || []).map((id) => byId.get(String(id))).filter(Boolean);
          // Defensive: backend is truth, but if the student list page hasn't
          // loaded a row yet, still show the card with the raw count.
          const shown = pendingStudents.length > 0 ? pendingStudents : [];
          return {
            key: `${t.batch_id}__${t.department_id || deptCode}__${t.stream}__${t.semester_number}`,
            batchId: t.batch_id,
            fileName: t.file_name,
            admissionYear: t.academic_year_code || '—',
            stream: t.stream,
            sem: t.semester_number,
            students: shown.length > 0 ? shown : (t.pending_student_ids || []).map((id) => ({ id })),
            pending: t.pending,
            total: t.total,
            placed: t.placed,
          };
        })
        .sort((a, b) =>
          String(a.admissionYear).localeCompare(String(b.admissionYear)) || Number(a.sem) - Number(b.sem)
        );
    }
    const map = new Map();
    students
      .filter((s) => !s.placement_finalized)
      .filter((s) => (deptCode ? s.department_code === deptCode : true))
      .forEach((s) => {
        const key = `${s.admission_year_code || '—'}__${s.is_direct_second_year ? 'DSE' : 'FY'}__${s.semester_number || '?'}`;
        if (!map.has(key)) {
          map.set(key, {
            key,
            batchId: null,
            fileName: null,
            admissionYear: s.admission_year_code || '—',
            stream: s.is_direct_second_year ? 'DSE' : 'FY',
            sem: s.semester_number,
            students: [],
            pending: 0,
            total: 0,
            placed: 0,
          });
        }
        map.get(key).students.push(s);
      });
    return [...map.values()].map((g) => ({ ...g, pending: g.students.length, total: g.students.length })).sort((a, b) =>
      String(a.admissionYear).localeCompare(String(b.admissionYear)) || Number(a.sem) - Number(b.sem)
    );
  }, [students, deptCode, intakes]);

  const deptDivisions = useMemo(() => {
    if (!selectedDept) return divisions;
    return divisions.filter((d) => String(d.department) === String(selectedDept) || String(d.department_id) === String(selectedDept));
  }, [divisions, selectedDept]);

  const studentsByDivision = useMemo(() => {
    const map = new Map();
    for (const s of students) {
      if (s.division_id) {
        const k = String(s.division_id);
        if (!map.has(k)) map.set(k, []);
        map.get(k).push(s);
      }
    }
    return map;
  }, [students]);

  const rosterOf = (divId) => studentsByDivision.get(String(divId)) || [];

  const unplacedStudentsBySem = useMemo(() => {
    const map = new Map();
    for (const s of students) {
      if (!s.placement_finalized && (!deptCode || s.department_code === deptCode)) {
        const sem = Number(s.semester_number);
        if (!map.has(sem)) map.set(sem, []);
        map.get(sem).push(s);
      }
    }
    return map;
  }, [students, deptCode]);

  // Candidates for "Add students": same dept + same sem, not yet confirmed,
  // sitting outside this division (covers later DSE imports merged into an FY class).
  const addCandidates = (div) => {
    const divSem = Number(div.semester_number ?? div.semester);
    const candidates = unplacedStudentsBySem.get(divSem) || [];
    return candidates.filter((s) => String(s.division_id) !== String(div.id));
  };

  const facultyName = (fid) => {
    if (!fid) return '';
    const f = faculties.find((x) => String(x.id) === String(fid) || String(x.user) === String(fid) || String(x.user_id) === String(fid));
    return f?.display_name || f?.name || f?.username || '—';
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
        const payload = { student_ids: group.students.map((s) => s.id) };
        if (group.batchId) payload.source_batch_id = group.batchId;
        const res = await academicApi.assignStudents(newId, payload);
        const movedCount = res.data?.moved?.length ?? group.students.length;
        const skippedCount = res.data?.skipped?.length || 0;
        setActionMsg(
          `Division ${createForm.name.trim().toUpperCase()} created — ${movedCount} student(s) placed${group.fileName ? ` from ${group.fileName}` : ''}.${skippedCount ? ` ${skippedCount} skipped (already placed elsewhere).` : ''} This import slice is now consumed.`
        );
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

  // ---- Place a pending batch slice into an EXISTING class (no new division).
  // Same merge endpoint as Add students, plus the batch id so the audit
  // trail records which import slice was consumed.
  const sameSemDivisions = (sem) => deptDivisions.filter(
    (d) => Number(d.semester_number ?? d.semester) === Number(sem)
  );
  const openPlaceModal = (group) => {
    const options = sameSemDivisions(group.sem);
    setPlaceTargetKey(group.key);
    setPlaceDivId(options[0]?.id || '');
    setShowAddModal(false);
  };
  const handlePlaceIntoExisting = async () => {
    const group = pendingGroups.find((g) => g.key === placeTargetKey);
    if (!group || !placeDivId || placing) return;
    if (!window.confirm(`Place ${group.pending ?? group.students.length} student(s) from ${group.fileName || 'this import'} into the selected class?`)) return;
    setPlacing(true);
    try {
      const payload = { student_ids: group.students.map((s) => s.id) };
      if (group.batchId) payload.source_batch_id = group.batchId;
      const res = await academicApi.assignStudents(placeDivId, payload);
      const skipped = res.data?.skipped?.length || 0;
      setActionMsg(`${res.data?.detail || 'Students placed.'}${skipped ? ` ${skipped} skipped (already placed elsewhere).` : ''}`);
      setActionError(null);
      setPlaceTargetKey(null);
      setPlaceDivId('');
      await loadAll();
    } catch (err) {
      setActionError(err.response?.data?.detail || 'Failed to place students.');
    } finally {
      setPlacing(false);
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

  // ---- Delete an empty class (backend also blocks seated/history classes)
  const [deletingDivId, setDeletingDivId] = useState(null);
  const handleDeleteDivision = async (div) => {
    const rosterCount = rosterOf(div.id).length;
    if (rosterCount > 0) return;
    if (!window.confirm(`Delete empty Division ${div.name} (Sem ${div.semester_number ?? ''})? This is recorded in the audit trail.`)) return;
    try {
      setDeletingDivId(div.id);
      setActionMsg(null);
      setActionError(null);
      await academicApi.deleteDivision(div.id);
      setActionMsg(`Division ${div.name} deleted.`);
      await loadAll(false);
    } catch (err) {
      setActionError(extractErrorMessage(err, 'Failed to delete division.'));
    } finally {
      setDeletingDivId(null);
    }
  };

  // ---- Class teacher change on a card
  const handleSetClassTeacher = async (div, teacherId) => {
    try {
      setActionMsg(null);
      setActionError(null);
      setSlotError(null);
      const res = await academicApi.updateDivision(div.id, { class_teacher: teacherId || null });
      const updated = res.data;
      setDivisions((prev) =>
        prev.map((d) => (String(d.id) === String(div.id) ? { ...d, ...updated } : d))
      );
      setActionMsg('Class teacher updated.');
    } catch (err) {
      const msg = extractErrorMessage(err, 'Failed to update class teacher.');
      setActionError(msg);
      setSlotError(msg);
      throw err;
    }
  };

  // ---- Expand card: roster is local; subjects + holders load lazily (same APIs as dashboard).
  // The two calls are independent: an assignments failure must never wipe
  // out good subjects (that once masqueraded as "no scheme published").
  // A failed subjects load is marked loaded:false + loadError so the popup
  // shows Retry instead of a permanently stale empty state.
  const ensureDivDetail = async (divId, force = false) => {
    if (divDetail[divId]?.loaded && !force) return;
    setLoadingDetail(true);
    try {
      const [subRes, asgRes] = await Promise.allSettled([
        academicApi.getDivisionSubjects(divId),
        facultyApi.getAssignments({ division_id: divId, is_active: true }),
      ]);
      if (subRes.status === 'rejected') {
        throw subRes.reason;
      }
      const asgOk = asgRes.status === 'fulfilled';
      setDivDetail((prev) => ({
        ...prev,
        [divId]: {
          subjects: subRes.value.data?.subjects || [],
          // Keep previously known holders when the assignments refetch
          // fails — wiping them would un-paint saved teachers.
          assignments: asgOk ? (asgRes.value.data?.results || asgRes.value.data || []) : (prev[divId]?.assignments || []),
          scheme: subRes.value.data?.scheme || null,
          loaded: true,
          assignError: asgOk ? null : 'Teacher assignments failed to load.',
        },
      }));
    } catch {
      setDivDetail((prev) => ({ ...prev, [divId]: { subjects: [], assignments: [], scheme: null, loaded: false, loadError: 'Failed to load subjects.' } }));
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
  // Always refetch on open so newly published schemes/subjects appear
  // immediately instead of showing a stale cached empty state.
  const openTeachersModal = async (div) => {
    setTeachersDivId(div.id);
    setSlotError(null);
    await ensureDivDetail(div.id, true);
  };

  const holderOf = (divId, subject) => {
    const list = divDetail[divId]?.assignments || [];
    return list.find((a) => a.scheme_subject === subject.id && a.role !== 'LAB_INSTRUCTOR' && a.is_active)
      || list.find((a) => (a.subject_code || '').toUpperCase() === (subject.course_code || '').toUpperCase() && a.role !== 'LAB_INSTRUCTOR' && a.is_active && !a.scheme_subject)
      || null;
  };

  const handleSaveSlot = async (divId, subject, facultyIdOverride) => {
    const facultyId = facultyIdOverride ?? slotEdit[subject.id];
    const holder = holderOf(divId, subject);

    // Unassign case: user selected empty string
    if (!facultyId) {
      if (!holder) {
        setSlotEdit((prev) => {
          const next = { ...prev };
          delete next[subject.id];
          return next;
        });
        return;
      }
      setSavingSlot(subject.id);
      setSlotError(null);
      try {
        await facultyApi.deactivateAssignment(holder.id, 'HOD unassigned subject teacher');
        setDivDetail((prev) => {
          const cur = prev[divId] || { subjects: [], assignments: [], scheme: null };
          return {
            ...prev,
            [divId]: {
              ...cur,
              assignments: (cur.assignments || []).filter((a) => String(a.id) !== String(holder.id)),
            },
          };
        });
        setActionMsg(`${subject.course_code} teacher unassigned.`);
        setActionError(null);
        setSlotEdit((prev) => {
          const next = { ...prev };
          delete next[subject.id];
          return next;
        });
      } catch (err) {
        const msg = extractErrorMessage(err, 'Failed to unassign teacher.');
        setSlotError(msg);
        setActionError(msg);
      } finally {
        setSavingSlot(null);
      }
      return;
    }

    if (holder && String(holder.faculty) === String(facultyId)) {
      setSlotEdit((prev) => {
        const next = { ...prev };
        delete next[subject.id];
        return next;
      });
      return;
    }
    setSavingSlot(subject.id);
    setSlotError(null);
    try {
      let deactivatedId = null;
      if (holder) {
        await facultyApi.deactivateAssignment(holder.id, 'HOD replaced subject teacher');
        deactivatedId = holder.id;
      }
      const created = await facultyApi.createAssignment({
        faculty: facultyId,
        division: divId,
        scheme_subject: subject.id,
        role: 'PRIMARY_FACULTY',
      });
      const row = created.data || {};
      // Optimistic paint: merge the new holder instantly so the name shows
      // immediately, then reconcile with the server below.
      setDivDetail((prev) => {
        const cur = prev[divId] || { subjects: [], assignments: [], scheme: null };
        const list = (cur.assignments || []).filter(
          (a) => String(a.id) !== String(deactivatedId) &&
            !(a.is_active && String(a.scheme_subject) === String(subject.id) &&
              a.role !== 'LAB_INSTRUCTOR' && String(a.id) !== String(row.id))
        );
        return {
          ...prev,
          [divId]: {
            ...cur, loaded: true, assignError: null,
            assignments: [...list, ...(row.id ? [{ ...row, is_active: true }] : [])],
          },
        };
      });
      setActionMsg(`${subject.course_code} teacher saved.`);
      setActionError(null);
      setSlotEdit((prev) => {
        const next = { ...prev };
        delete next[subject.id];
        return next;
      });
      // Reconcile with server truth (independent calls; never wipes holders).
      await ensureDivDetail(divId, true);
    } catch (err) {
      const msg = extractErrorMessage(err, 'Failed to save teacher.');
      // Modal-level error: the page banner sits behind the open popup and
      // the user would otherwise never see why the name didn't appear.
      setSlotError(msg);
      setActionError(msg);
    } finally {
      setSavingSlot(null);
    }
  };

  if (loading && divisions.length === 0) {
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
                Each file batch is single-use: once its students are placed the card disappears and cannot be reused.
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
                    <th>Import File</th>
                    <th>Academic Year</th>
                    <th>Program / Stream</th>
                    <th>Year - Sem</th>
                    <th style={{ textAlign: 'center' }}>Pending / Total</th>
                    <th style={{ textAlign: 'center' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingGroups.map((g) => {
                    const targets = sameSemDivisions(g.sem);
                    return (
                    <tr key={g.key}>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.76rem' }}>{g.fileName || '—'}</td>
                      <td style={{ fontWeight: 700 }}>{g.admissionYear}</td>
                      <td>
                        {deptCode} ({g.stream === 'DSE' ? 'DSY Lateral' : 'Regular'})
                      </td>
                      <td>{semLabel(semesters, g.sem)}</td>
                      <td style={{ textAlign: 'center', fontWeight: 700 }}>{g.pending ?? g.students.length}{g.total ? ` / ${g.total}` : ''}</td>
                      <td style={{ textAlign: 'center' }}>
                        {canManage && targets.length > 0 ? (
                          <button
                            type="button"
                            className="edvana-btn edvana-btn-secondary"
                            onClick={() => openPlaceModal(g)}
                            title={`Place into existing ${semLabel(semesters, g.sem)} class instead of creating a new division`}
                            style={{ height: '32px', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
                          >
                            <Plus size={13} /> Add to existing class
                          </button>
                        ) : (
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Create a division first</span>
                        )}
                      </td>
                    </tr>
                    );
                  })}
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
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => toggleExpand(d)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(d); } }}
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
                      {strength === 0 && canManage && (
                        <button
                          type="button"
                          title="Delete empty class"
                          disabled={String(deletingDivId) === String(d.id)}
                          onClick={(e) => { e.stopPropagation(); handleDeleteDivision(d); }}
                          style={{
                            background: '#fff', border: '1px solid #fecaca', borderRadius: '8px',
                            padding: '0.35rem', cursor: 'pointer', display: 'inline-flex',
                            color: '#b91c1c', opacity: String(deletingDivId) === String(d.id) ? 0.5 : 1,
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>

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
                                        className="edvana-select"
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
              <span>{departments[0] ? `${departments[0].name} (${departments[0].code})` : 'No department mapped'}</span>
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
                {slotError && (
                  <div style={{ marginBottom: '0.75rem', padding: '0.7rem 0.9rem', fontSize: '0.8rem', color: '#991b1b', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px' }}>
                    {slotError}
                  </div>
                )}                <div style={{ overflowX: 'auto', border: '1px solid #e8eef6', borderRadius: '14px' }}>
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
                            value={slotEdit[ctKey] !== undefined ? slotEdit[ctKey] : (div.class_teacher_faculty_id || div.class_teacher || '')}
                            faculties={faculties}
                            saving={savingSlot === ctKey}
                            placeholder={div.class_teacher_name ? 'Change teacher…' : 'Assign teacher…'}
                            onEdit={() => setSlotEdit((prev) => ({ ...prev, [ctKey]: div.class_teacher_faculty_id || div.class_teacher || '' }))}
                            onCancelEdit={() => setSlotEdit((prev) => {
                              const next = { ...prev };
                              delete next[ctKey];
                              return next;
                            })}
                            onPick={async (fid) => {
                              setSavingSlot(ctKey);
                              try {
                                await handleSetClassTeacher(div, fid);
                                setSlotEdit((prev) => {
                                  const next = { ...prev };
                                  delete next[ctKey];
                                  return next;
                                });
                              } catch {
                                // Error already set in handleSetClassTeacher
                              } finally {
                                setSavingSlot(null);
                              }
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
                                holderLabel={holder ? (holder.faculty_name || facultyName(holder.faculty)) : ''}
                                editing={editing}
                                value={slotEdit[sub.id] !== undefined ? slotEdit[sub.id] : (holder ? String(holder.faculty) : '')}
                                faculties={faculties}
                                saving={savingSlot === sub.id}
                                placeholder="Assign teacher…"
                                currentSubjectCode={sub.course_code}
                                assignedHolders={detail?.assignments || []}
                                onEdit={() => setSlotEdit((prev) => ({ ...prev, [sub.id]: holder ? String(holder.faculty) : '' }))}
                                onCancelEdit={() => setSlotEdit((prev) => {
                                  const next = { ...prev };
                                  delete next[sub.id];
                                  return next;
                                })}
                                onPick={(fid) => handleSaveSlot(div.id, sub, fid)}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {!loadingDetail && detail?.assignError && (
                  <div style={{ marginTop: '0.9rem', padding: '0.85rem 1rem', fontSize: '0.8rem', color: '#b45309', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '12px' }}>
                    {detail.assignError} Existing holders may be missing —{' '}
                    <button type="button" onClick={() => ensureDivDetail(div.id, true)} style={{ background: 'none', border: 'none', padding: 0, color: '#1E60DC', fontWeight: 700, cursor: 'pointer', fontSize: '0.8rem' }}>
                      Retry
                    </button>
                  </div>
                )}
                {!loadingDetail && (!detail?.loaded || detail.subjects.length === 0) && (
                  <div style={{ marginTop: '0.9rem', padding: '0.85rem 1rem', fontSize: '0.8rem', color: '#64748b', background: '#f8fafc', border: '1px solid #e8eef6', borderRadius: '12px' }}>
                    {detail?.loadError ? (
                      <span>
                        {detail.loadError} Check your connection and{' '}
                        <button type="button" onClick={() => ensureDivDetail(div.id, true)} style={{ background: 'none', border: 'none', padding: 0, color: '#1E60DC', fontWeight: 700, cursor: 'pointer', fontSize: '0.8rem' }}>
                          Retry
                        </button>
                      </span>
                    ) : detail?.scheme
                      ? `Scheme ${detail.scheme.code} v${detail.scheme.version} is published, but it has no subjects for Sem ${div.semester_number ?? ''} yet — ask Sysadmin to add the Sem ${div.semester_number ?? ''} subjects under Schemes & Subjects.`
                      : 'No scheme subjects published for this semester yet — publish the scheme to assign subject teachers.'}
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
        const inputStyle = { width: '100%', maxWidth: '100%', minHeight: '42px', marginTop: '0.3rem', borderRadius: '10px', boxSizing: 'border-box' };
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
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '0.9rem 1rem', marginBottom: '0.9rem' }}>
                <div>
                  <label style={labelStyle}>Academic Year{req}</label>
                  <select
                    className="edvana-select"
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
                    className="edvana-select"
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
                    className="edvana-select"
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
                    maxLength={5}
                    value={createForm.name}
                    onChange={(e) => setCreateForm((p) => ({ ...p, name: e.target.value.toUpperCase().slice(0, 5) }))}
                    placeholder="e.g. A, B, R"
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
                    className="edvana-select"
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
                <label style={labelStyle}>Import to place <span style={{ fontWeight: 400, color: '#64748b' }}>(single-use — consumed on create)</span></label>
                <select
                  className="edvana-select"
                  value={createForm.intakeKey}
                  onChange={(e) => setCreateForm((p) => ({ ...p, intakeKey: e.target.value }))}
                  style={inputStyle}
                >
                  <option value="">— Create empty, place later —</option>
                  {pendingGroups.map((g) => (
                    <option key={g.key} value={g.key}>
                      {g.fileName ? `${g.fileName} • ` : ''}{g.admissionYear} • {g.stream === 'DSE' ? 'DSY' : 'Regular'} • Sem {g.sem} • {g.pending ?? g.students.length} pending{g.total ? `/${g.total}` : ''}
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
                    {cIntake ? ` ${cIntake.pending ?? cIntake.students.length} student(s) from ${cIntake.fileName || 'the selected import'} will be placed (single-use).` : ''}
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

      {/* Place pending batch slice into an existing class (no new division) */}
      {placeTargetKey && (() => {
        const group = pendingGroups.find((g) => g.key === placeTargetKey);
        if (!group) return null;
        const options = sameSemDivisions(group.sem);
        const count = group.pending ?? group.students.length;
        return (
          <Modal isOpen onClose={() => { setPlaceTargetKey(null); setPlaceDivId(''); }} title={`Add to existing class — Sem ${group.sem}`} maxWidth="520px">
            <div style={{ padding: '0.5rem 0' }}>
              <div style={{ fontSize: '0.85rem', color: '#334155', marginBottom: '0.75rem', lineHeight: 1.55 }}>
                Place <strong>{count} student(s)</strong> from{' '}
                <span style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{group.fileName || 'this import'}</span>{' '}
                into an existing {semLabel(semesters, group.sem)} class. No new division is created; the batch slice is consumed.
              </div>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: '#0f172a' }}>Existing class</label>
              <select
                className="edvana-select"
                value={placeDivId}
                onChange={(e) => setPlaceDivId(e.target.value)}
                style={{ width: '100%', minHeight: '42px', marginTop: '0.3rem', borderRadius: '10px' }}
              >
                <option value="">Select class…</option>
                {options.map((d) => (
                  <option key={d.id} value={d.id}>
                    Div {d.name} ({d.academic_year_code || ''}) — {d.enrolled_count ?? rosterOf(d.id).length} seated{d.class_teacher_name ? ` — ${d.class_teacher_name}` : ' — no teacher'}
                  </option>
                ))}
              </select>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem', borderTop: '1px solid #f1f5f9', paddingTop: '1rem' }}>
                <button type="button" className="edvana-btn edvana-btn-secondary" onClick={() => { setPlaceTargetKey(null); setPlaceDivId(''); }}>
                  Cancel
                </button>
                <button type="button" className="edvana-btn edvana-btn-primary" disabled={placing || !placeDivId} onClick={handlePlaceIntoExisting}>
                  {placing ? 'Placing…' : `Confirm (${count})`}
                </button>
              </div>
            </div>
          </Modal>
        );
      })()}
    </>
  );
}
