"""initial_schema

Revision ID: 0001
Revises: 
"""
from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_table('calendar_days',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('day_type', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint('day', name=op.f('pk_calendar_days'))
    )
    op.create_table('company_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_company_settings'))
    )
    op.create_table('eval_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=False),
    sa.Column('case_id', sa.String(length=32), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('numeric_ok', sa.Boolean(), nullable=True),
    sa.Column('semantic_ok', sa.Boolean(), nullable=True),
    sa.Column('leaked', sa.Boolean(), nullable=False),
    sa.Column('refused_ok', sa.Boolean(), nullable=True),
    sa.Column('action_ok', sa.Boolean(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_eval_runs'))
    )
    op.create_index(op.f('ix_eval_runs_run_id'), 'eval_runs', ['run_id'], unique=False)
    op.create_table('job_grades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('grade', sa.Integer(), nullable=False),
    sa.Column('step', sa.Integer(), nullable=False),
    sa.Column('title_band', sa.String(length=32), nullable=False),
    sa.Column('salary_min', sa.Integer(), nullable=False),
    sa.Column('salary_max', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_grades')),
    sa.UniqueConstraint('grade', 'step', name=op.f('uq_job_grades_grade'))
    )
    op.create_table('law_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rule_key', sa.String(length=64), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source_ref', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_law_rules')),
    sa.UniqueConstraint('rule_key', 'effective_from', name=op.f('uq_law_rules_rule_key'))
    )
    op.create_table('leave_types',
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('pay_ratio', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('quota_rule_key', sa.String(length=64), nullable=True),
    sa.Column('min_unit_hours', sa.Numeric(precision=4, scale=1), nullable=False),
    sa.Column('counts_calendar_days', sa.Boolean(), nullable=False),
    sa.Column('requires_attachment', sa.Boolean(), nullable=False),
    sa.Column('reason_sensitivity', sa.String(length=2), nullable=False),
    sa.Column('law_ref', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('code', name=op.f('pk_leave_types'))
    )
    op.create_table('org_units',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('path', sa.String(length=255), nullable=False),
    sa.Column('head_emp_id', sa.Integer(), nullable=True),
    sa.Column('site', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['org_units.id'], name=op.f('fk_org_units_parent_id_org_units')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_org_units')),
    sa.UniqueConstraint('code', name=op.f('uq_org_units_code'))
    )
    op.create_index('ix_org_units_path_prefix', 'org_units', ['path'], unique=False, postgresql_ops={'path': 'text_pattern_ops'})
    op.create_table('policy_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('version', sa.String(length=16), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_policy_documents'))
    )
    op.create_table('work_schedules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('daily_hours', sa.Integer(), nullable=False),
    sa.Column('work_blocks', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('flex_start_from', sa.String(length=5), nullable=False),
    sa.Column('flex_start_to', sa.String(length=5), nullable=False),
    sa.Column('rest_day_weekday', sa.Integer(), nullable=False),
    sa.Column('regular_leave_weekday', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_work_schedules')),
    sa.UniqueConstraint('code', name=op.f('uq_work_schedules_code'))
    )
    op.create_table('employees',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_no', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('english_name', sa.String(length=64), nullable=True),
    sa.Column('gender', sa.String(length=1), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('national_id', sa.String(length=10), nullable=False),
    sa.Column('email', sa.String(length=128), nullable=False),
    sa.Column('phone_ext', sa.String(length=8), nullable=True),
    sa.Column('mobile', sa.String(length=16), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('org_unit_id', sa.Integer(), nullable=False),
    sa.Column('manager_id', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=64), nullable=False),
    sa.Column('job_grade_id', sa.Integer(), nullable=False),
    sa.Column('employment_type', sa.String(length=16), nullable=False),
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('hire_date', sa.Date(), nullable=False),
    sa.Column('seniority_start_date', sa.Date(), nullable=False),
    sa.Column('probation_end_date', sa.Date(), nullable=True),
    sa.Column('termination_date', sa.Date(), nullable=True),
    sa.Column('termination_reason', sa.String(length=32), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['job_grade_id'], ['job_grades.id'], name=op.f('fk_employees_job_grade_id_job_grades')),
    sa.ForeignKeyConstraint(['manager_id'], ['employees.id'], name=op.f('fk_employees_manager_id_employees')),
    sa.ForeignKeyConstraint(['org_unit_id'], ['org_units.id'], name=op.f('fk_employees_org_unit_id_org_units')),
    sa.ForeignKeyConstraint(['schedule_id'], ['work_schedules.id'], name=op.f('fk_employees_schedule_id_work_schedules')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_employees')),
    sa.UniqueConstraint('email', name=op.f('uq_employees_email')),
    sa.UniqueConstraint('emp_no', name=op.f('uq_employees_emp_no'))
    )
    op.create_table('policy_chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('doc_id', sa.Integer(), nullable=False),
    sa.Column('section_path', sa.String(length=128), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=512), nullable=False),
    sa.ForeignKeyConstraint(['doc_id'], ['policy_documents.id'], name=op.f('fk_policy_chunks_doc_id_policy_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_policy_chunks'))
    )
    op.create_index(op.f('ix_policy_chunks_doc_id'), 'policy_chunks', ['doc_id'], unique=False)
    op.create_index('ix_policy_chunks_text_trgm', 'policy_chunks', ['text'], unique=False, postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'})
    op.create_table('attendance_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('work_date', sa.Date(), nullable=False),
    sa.Column('clock_in', sa.DateTime(timezone=True), nullable=True),
    sa.Column('clock_out', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('note', sa.String(length=128), nullable=True),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_attendance_records_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attendance_records')),
    sa.UniqueConstraint('emp_id', 'work_date', name=op.f('uq_attendance_records_emp_id'))
    )
    op.create_table('benefit_claims',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('benefit_code', sa.String(length=32), nullable=False),
    sa.Column('claim_year', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('event_date', sa.Date(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_benefit_claims_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_benefit_claims'))
    )
    op.create_index(op.f('ix_benefit_claims_emp_id'), 'benefit_claims', ['emp_id'], unique=False)
    op.create_table('dependents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.Column('relation', sa.String(length=16), nullable=False),
    sa.Column('birth_date', sa.Date(), nullable=False),
    sa.Column('nhi_enrolled', sa.Boolean(), nullable=False),
    sa.Column('group_insurance_enrolled', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_dependents_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_dependents'))
    )
    op.create_index(op.f('ix_dependents_emp_id'), 'dependents', ['emp_id'], unique=False)
    op.create_table('employment_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('event', sa.String(length=16), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_employment_history_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_employment_history'))
    )
    op.create_index(op.f('ix_employment_history_emp_id'), 'employment_history', ['emp_id'], unique=False)
    op.create_table('insurance_enrollments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('labor_insured_salary', sa.Integer(), nullable=False),
    sa.Column('health_insured_salary', sa.Integer(), nullable=False),
    sa.Column('pension_contribution_wage', sa.Integer(), nullable=False),
    sa.Column('pension_voluntary_rate', sa.Numeric(precision=4, scale=2), nullable=False),
    sa.Column('nhi_dependents', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_insurance_enrollments_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_insurance_enrollments'))
    )
    op.create_index(op.f('ix_insurance_enrollments_emp_id'), 'insurance_enrollments', ['emp_id'], unique=False)
    op.create_table('leave_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('leave_type', sa.String(length=32), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hours', sa.Numeric(precision=6, scale=1), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('deputy_emp_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('approver_id', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('created_via', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('end_at > start_at', name=op.f('ck_leave_requests_time_order')),
    sa.ForeignKeyConstraint(['approver_id'], ['employees.id'], name=op.f('fk_leave_requests_approver_id_employees')),
    sa.ForeignKeyConstraint(['deputy_emp_id'], ['employees.id'], name=op.f('fk_leave_requests_deputy_emp_id_employees')),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_leave_requests_emp_id_employees')),
    sa.ForeignKeyConstraint(['leave_type'], ['leave_types.code'], name=op.f('fk_leave_requests_leave_type_leave_types')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leave_requests'))
    )
    op.create_index(op.f('ix_leave_requests_emp_id'), 'leave_requests', ['emp_id'], unique=False)
    op.create_index('ix_leave_requests_status_approver', 'leave_requests', ['status', 'approver_id'], unique=False)
    op.create_table('overtime_records',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('work_date', sa.Date(), nullable=False),
    sa.Column('day_type', sa.String(length=20), nullable=False),
    sa.Column('hours', sa.Numeric(precision=4, scale=1), nullable=False),
    sa.Column('compensation', sa.String(length=10), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('approver_id', sa.Integer(), nullable=True),
    sa.Column('comp_time_expires_on', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['approver_id'], ['employees.id'], name=op.f('fk_overtime_records_approver_id_employees')),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_overtime_records_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_overtime_records'))
    )
    op.create_index(op.f('ix_overtime_records_emp_id'), 'overtime_records', ['emp_id'], unique=False)
    op.create_table('payslips',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('pay_month', sa.String(length=7), nullable=False),
    sa.Column('gross', sa.Integer(), nullable=False),
    sa.Column('deductions', sa.Integer(), nullable=False),
    sa.Column('net', sa.Integer(), nullable=False),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_payslips_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payslips')),
    sa.UniqueConstraint('emp_id', 'pay_month', name=op.f('uq_payslips_emp_id'))
    )
    op.create_table('salary_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('base_monthly', sa.Integer(), nullable=False),
    sa.Column('regular_allowances', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('attendance_bonus', sa.Integer(), nullable=False),
    sa.Column('bank_account_masked', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_salary_profiles_emp_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_salary_profiles')),
    sa.UniqueConstraint('emp_id', 'effective_from', name=op.f('uq_salary_profiles_emp_id'))
    )
    op.create_index(op.f('ix_salary_profiles_emp_id'), 'salary_profiles', ['emp_id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=True),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], name=op.f('fk_users_employee_id_employees')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('employee_id', name=op.f('uq_users_employee_id')),
    sa.UniqueConstraint('username', name=op.f('uq_users_username'))
    )
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('scope', sa.String(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_api_tokens_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_api_tokens_token_hash'))
    )
    op.create_index(op.f('ix_api_tokens_user_id'), 'api_tokens', ['user_id'], unique=False)
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('leave_ledger',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('emp_id', sa.Integer(), nullable=False),
    sa.Column('leave_type', sa.String(length=32), nullable=False),
    sa.Column('period_key', sa.String(length=32), nullable=False),
    sa.Column('delta_hours', sa.Numeric(precision=7, scale=1), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('ref_request_id', sa.Integer(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_leave_ledger_created_by_users')),
    sa.ForeignKeyConstraint(['emp_id'], ['employees.id'], name=op.f('fk_leave_ledger_emp_id_employees')),
    sa.ForeignKeyConstraint(['leave_type'], ['leave_types.code'], name=op.f('fk_leave_ledger_leave_type_leave_types')),
    sa.ForeignKeyConstraint(['ref_request_id'], ['leave_requests.id'], name=op.f('fk_leave_ledger_ref_request_id_leave_requests')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_leave_ledger'))
    )
    op.create_index('ix_leave_ledger_emp_type_period', 'leave_ledger', ['emp_id', 'leave_type', 'period_key'], unique=False)
    op.create_table('payslip_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payslip_id', sa.Integer(), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=32), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('calc_note', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['payslip_id'], ['payslips.id'], name=op.f('fk_payslip_items_payslip_id_payslips')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payslip_items'))
    )
    op.create_index(op.f('ix_payslip_items_payslip_id'), 'payslip_items', ['payslip_id'], unique=False)
    op.create_table('user_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('scope_org_unit_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['scope_org_unit_id'], ['org_units.id'], name=op.f('fk_user_roles_scope_org_unit_id_org_units')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_roles_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_roles')),
    sa.UniqueConstraint('user_id', 'role', 'scope_org_unit_id', name=op.f('uq_user_roles_user_id'))
    )
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('roles', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('channel', sa.String(length=8), nullable=False),
    sa.Column('event', sa.String(length=32), nullable=False),
    sa.Column('question', sa.Text(), nullable=True),
    sa.Column('intent', sa.String(length=48), nullable=True),
    sa.Column('model', sa.String(length=64), nullable=True),
    sa.Column('routed_by', sa.String(length=32), nullable=True),
    sa.Column('tools', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('denied', sa.Boolean(), nullable=False),
    sa.Column('deny_reason', sa.String(length=128), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_read_tokens', sa.Integer(), nullable=False),
    sa.Column('cache_write_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('grounding_ok', sa.Boolean(), nullable=True),
    sa.Column('conversation_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_audit_log_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_log_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index(op.f('ix_audit_log_ts'), 'audit_log', ['ts'], unique=False)
    op.create_index(op.f('ix_audit_log_user_id'), 'audit_log', ['user_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_table('tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('requester_id', sa.Integer(), nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('context_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('assignee_id', sa.Integer(), nullable=True),
    sa.Column('confidential', sa.Boolean(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['assignee_id'], ['users.id'], name=op.f('fk_tickets_assignee_id_users')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_tickets_conversation_id_conversations')),
    sa.ForeignKeyConstraint(['requester_id'], ['users.id'], name=op.f('fk_tickets_requester_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tickets'))
    )
    op.create_index(op.f('ix_tickets_requester_id'), 'tickets', ['requester_id'], unique=False)
    # org_units 與 employees 互相參照，FK 需在兩表都建立後再加
    op.create_foreign_key(op.f('fk_org_units_head_emp_id_employees'), 'org_units', 'employees', ['head_emp_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_org_units_head_emp_id_employees'), 'org_units', type_='foreignkey')
    op.drop_index(op.f('ix_tickets_requester_id'), table_name='tickets')
    op.drop_table('tickets')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_audit_log_user_id'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_ts'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_user_roles_user_id'), table_name='user_roles')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_payslip_items_payslip_id'), table_name='payslip_items')
    op.drop_table('payslip_items')
    op.drop_index('ix_leave_ledger_emp_type_period', table_name='leave_ledger')
    op.drop_table('leave_ledger')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_api_tokens_user_id'), table_name='api_tokens')
    op.drop_table('api_tokens')
    op.drop_table('users')
    op.drop_index(op.f('ix_salary_profiles_emp_id'), table_name='salary_profiles')
    op.drop_table('salary_profiles')
    op.drop_table('payslips')
    op.drop_index(op.f('ix_overtime_records_emp_id'), table_name='overtime_records')
    op.drop_table('overtime_records')
    op.drop_index('ix_leave_requests_status_approver', table_name='leave_requests')
    op.drop_index(op.f('ix_leave_requests_emp_id'), table_name='leave_requests')
    op.drop_table('leave_requests')
    op.drop_index(op.f('ix_insurance_enrollments_emp_id'), table_name='insurance_enrollments')
    op.drop_table('insurance_enrollments')
    op.drop_index(op.f('ix_employment_history_emp_id'), table_name='employment_history')
    op.drop_table('employment_history')
    op.drop_index(op.f('ix_dependents_emp_id'), table_name='dependents')
    op.drop_table('dependents')
    op.drop_index(op.f('ix_benefit_claims_emp_id'), table_name='benefit_claims')
    op.drop_table('benefit_claims')
    op.drop_table('attendance_records')
    op.drop_index('ix_policy_chunks_text_trgm', table_name='policy_chunks', postgresql_using='gin', postgresql_ops={'text': 'gin_trgm_ops'})
    op.drop_index(op.f('ix_policy_chunks_doc_id'), table_name='policy_chunks')
    op.drop_table('policy_chunks')
    op.drop_table('employees')
    op.drop_table('work_schedules')
    op.drop_table('policy_documents')
    op.drop_index('ix_org_units_path_prefix', table_name='org_units', postgresql_ops={'path': 'text_pattern_ops'})
    op.drop_table('org_units')
    op.drop_table('leave_types')
    op.drop_table('law_rules')
    op.drop_table('job_grades')
    op.drop_index(op.f('ix_eval_runs_run_id'), table_name='eval_runs')
    op.drop_table('eval_runs')
    op.drop_table('company_settings')
    op.drop_table('calendar_days')
