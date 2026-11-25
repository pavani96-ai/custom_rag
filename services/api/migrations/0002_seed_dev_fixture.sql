-- Local development fixture: one user, one workspace, one collection.
-- Fixed UUIDs keep the fixture stable across resets. Do not run in production.

INSERT INTO users (id, email, display_name) VALUES
    ('00000000-0000-4000-8000-000000000001', 'developer@example.local', 'Local developer');

INSERT INTO workspaces (id, name) VALUES
    ('00000000-0000-4000-8000-000000000002', 'Local workspace');

INSERT INTO workspace_members (workspace_id, user_id, role) VALUES
    ('00000000-0000-4000-8000-000000000002', '00000000-0000-4000-8000-000000000001', 'owner');

INSERT INTO collections (id, workspace_id, title, description) VALUES
    ('00000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000002',
     'Local collection', 'Development fixture');
