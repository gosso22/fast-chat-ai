# Requirements Document

## Introduction

This document defines the requirements for an Admin Dashboard UI for the Fast Chat RAG application. The dashboard enables administrators to manage environments (isolated knowledge bases) and user roles. The UI must be mobile-friendly, responsive, and easy to use, following the existing React/TypeScript/Tailwind CSS patterns in the frontend codebase.

## Glossary

- **Admin_Dashboard**: The main administrative interface providing access to environment and role management features
- **Environment**: An isolated knowledge base containing documents and associated user roles
- **User_Role**: A permission assignment linking a user to an environment with a specific role (admin or chat_user)
- **Environment_List**: A component displaying all environments with summary information
- **Role_List**: A component displaying user role assignments for an environment
- **Environment_Form**: A form component for creating or editing environments
- **Role_Form**: A form component for assigning or updating user roles
- **Confirmation_Dialog**: A modal dialog requesting user confirmation before destructive actions
- **Mobile_Navigation**: A collapsible navigation menu optimized for mobile devices
- **Toast_Notification**: A temporary message displayed to provide feedback on user actions

## Requirements

### Requirement 1: Admin Dashboard Navigation

**User Story:** As an admin, I want to access the admin dashboard from the main navigation, so that I can manage environments and user roles.

#### Acceptance Criteria

1. THE Header SHALL display an "Admin" navigation link alongside existing Chat and Documents links
2. WHEN the Admin link is clicked, THE Router SHALL navigate to the /admin route
3. THE Admin_Dashboard SHALL display a tabbed or segmented interface with "Environments" and "Roles" sections
4. WHILE on mobile viewport (width < 768px), THE Mobile_Navigation SHALL collapse navigation links into a hamburger menu
5. WHEN the hamburger menu icon is tapped, THE Mobile_Navigation SHALL expand to show all navigation links

### Requirement 2: Environment List View

**User Story:** As an admin, I want to view all environments in a list, so that I can see and manage existing knowledge bases.

#### Acceptance Criteria

1. WHEN the Environments tab is active, THE Environment_List SHALL fetch and display all environments from GET /api/environments
2. THE Environment_List SHALL display each environment's name, description, created_by, and created_at fields
3. THE Environment_List SHALL display a document count for each environment
4. WHILE environments are loading, THE Environment_List SHALL display a loading indicator
5. IF the environments fetch fails, THEN THE Environment_List SHALL display an error message with a retry button
6. IF no environments exist, THEN THE Environment_List SHALL display an empty state message with a prompt to create one
7. WHILE on mobile viewport, THE Environment_List SHALL display environments as stacked cards instead of a table

### Requirement 3: Create Environment

**User Story:** As an admin, I want to create new environments, so that I can set up isolated knowledge bases for different use cases.

#### Acceptance Criteria

1. THE Environment_List SHALL display a "Create Environment" button
2. WHEN the Create Environment button is clicked, THE Environment_Form SHALL open in create mode
3. THE Environment_Form SHALL include required name field (1-255 characters) and optional description field
4. THE Environment_Form SHALL validate that name is not empty before submission
5. WHEN the form is submitted with valid data, THE Environment_Form SHALL POST to /api/environments
6. IF environment creation succeeds, THEN THE Toast_Notification SHALL display a success message and THE Environment_List SHALL refresh
7. IF environment creation fails with 409 conflict, THEN THE Environment_Form SHALL display "Environment name already exists" error
8. IF environment creation fails with other errors, THEN THE Toast_Notification SHALL display the error message

### Requirement 4: Edit Environment

**User Story:** As an admin, I want to edit existing environments, so that I can update their names and descriptions.

#### Acceptance Criteria

1. THE Environment_List SHALL display an edit action for each environment
2. WHEN the edit action is clicked, THE Environment_Form SHALL open in edit mode with current values populated
3. WHEN the form is submitted with valid data, THE Environment_Form SHALL PUT to /api/environments/{environment_id}
4. IF environment update succeeds, THEN THE Toast_Notification SHALL display a success message and THE Environment_List SHALL refresh
5. IF environment update fails with 409 conflict, THEN THE Environment_Form SHALL display "Environment name already exists" error

### Requirement 5: Delete Environment

**User Story:** As an admin, I want to delete environments, so that I can remove unused knowledge bases.

#### Acceptance Criteria

1. THE Environment_List SHALL display a delete action for each environment
2. WHEN the delete action is clicked, THE Confirmation_Dialog SHALL open with a warning about cascading document deletion
3. THE Confirmation_Dialog SHALL display the environment name and document count that will be deleted
4. WHEN the user confirms deletion, THE Admin_Dashboard SHALL DELETE to /api/environments/{environment_id}
5. IF environment deletion succeeds, THEN THE Toast_Notification SHALL display a success message including deleted document count
6. IF environment deletion fails, THEN THE Toast_Notification SHALL display the error message
7. WHEN the user cancels deletion, THE Confirmation_Dialog SHALL close without making changes

### Requirement 6: Role List View

**User Story:** As an admin, I want to view all user role assignments, so that I can see who has access to which environments.

#### Acceptance Criteria

1. WHEN the Roles tab is active, THE Role_List SHALL fetch and display all roles from GET /api/roles
2. THE Role_List SHALL display each role's user_id, role type, environment name, and created_at
3. THE Role_List SHALL support filtering by environment using a dropdown selector
4. THE Role_List SHALL support filtering by user_id using a search input
5. WHILE roles are loading, THE Role_List SHALL display a loading indicator
6. IF the roles fetch fails, THEN THE Role_List SHALL display an error message with a retry button
7. IF no roles match the current filters, THEN THE Role_List SHALL display an empty state message
8. WHILE on mobile viewport, THE Role_List SHALL display roles as stacked cards instead of a table

### Requirement 7: Assign Role

**User Story:** As an admin, I want to assign roles to users for specific environments, so that I can control access to knowledge bases.

#### Acceptance Criteria

1. THE Role_List SHALL display an "Assign Role" button
2. WHEN the Assign Role button is clicked, THE Role_Form SHALL open in create mode
3. THE Role_Form SHALL include required user_id field, role dropdown (admin/chat_user), and environment dropdown
4. THE Role_Form SHALL validate that all required fields are filled before submission
5. WHEN the form is submitted with valid data, THE Role_Form SHALL POST to /api/roles
6. IF role assignment succeeds, THEN THE Toast_Notification SHALL display a success message and THE Role_List SHALL refresh
7. IF role assignment fails with 409 conflict, THEN THE Role_Form SHALL display "User already has a role in this environment" error
8. IF role assignment fails with 404, THEN THE Role_Form SHALL display "Environment not found" error

### Requirement 8: Update Role

**User Story:** As an admin, I want to update user roles, so that I can change permissions as needed.

#### Acceptance Criteria

1. THE Role_List SHALL display an edit action for each role
2. WHEN the edit action is clicked, THE Role_Form SHALL open in edit mode showing current role type
3. THE Role_Form in edit mode SHALL only allow changing the role type (admin/chat_user)
4. WHEN the form is submitted, THE Role_Form SHALL PUT to /api/roles/{role_id}
5. IF role update succeeds, THEN THE Toast_Notification SHALL display a success message and THE Role_List SHALL refresh

### Requirement 9: Remove Role

**User Story:** As an admin, I want to remove role assignments, so that I can revoke user access to environments.

#### Acceptance Criteria

1. THE Role_List SHALL display a delete action for each role
2. WHEN the delete action is clicked, THE Confirmation_Dialog SHALL open with details about the role being removed
3. THE Confirmation_Dialog SHALL display the user_id, role type, and environment name
4. WHEN the user confirms deletion, THE Admin_Dashboard SHALL DELETE to /api/roles/{role_id}
5. IF role deletion succeeds, THEN THE Toast_Notification SHALL display a success message
6. WHEN the user cancels deletion, THE Confirmation_Dialog SHALL close without making changes

### Requirement 10: Responsive Layout

**User Story:** As an admin, I want the dashboard to work well on all devices, so that I can manage the system from my phone or tablet.

#### Acceptance Criteria

1. WHILE viewport width is >= 1024px (desktop), THE Admin_Dashboard SHALL display content in a wide layout with side-by-side elements where appropriate
2. WHILE viewport width is >= 768px and < 1024px (tablet), THE Admin_Dashboard SHALL adjust spacing and element sizes for medium screens
3. WHILE viewport width is < 768px (mobile), THE Admin_Dashboard SHALL stack elements vertically and use full-width components
4. THE Admin_Dashboard SHALL use touch-friendly tap targets (minimum 44x44px) for all interactive elements
5. THE Environment_Form and Role_Form SHALL display as full-screen modals on mobile and centered dialogs on desktop
6. THE Confirmation_Dialog SHALL be centered and appropriately sized for all viewport sizes

### Requirement 11: Loading and Error States

**User Story:** As an admin, I want clear feedback on loading and error states, so that I understand what is happening in the system.

#### Acceptance Criteria

1. WHILE any API request is in progress, THE Admin_Dashboard SHALL display appropriate loading indicators
2. WHILE a form submission is in progress, THE Admin_Dashboard SHALL disable the submit button and show a loading state
3. IF an API request fails, THEN THE Admin_Dashboard SHALL display a user-friendly error message
4. THE Toast_Notification SHALL auto-dismiss after 5 seconds for success messages
5. THE Toast_Notification SHALL remain visible until dismissed for error messages
6. THE Toast_Notification SHALL be positioned at the bottom of the viewport on mobile and top-right on desktop

### Requirement 12: Accessibility

**User Story:** As an admin using assistive technology, I want the dashboard to be accessible, so that I can manage the system effectively.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL use semantic HTML elements (nav, main, section, button, form)
2. THE Admin_Dashboard SHALL provide appropriate ARIA labels for interactive elements
3. THE Admin_Dashboard SHALL support keyboard navigation for all interactive elements
4. THE Confirmation_Dialog SHALL trap focus while open and return focus to the trigger element when closed
5. THE Admin_Dashboard SHALL maintain a minimum color contrast ratio of 4.5:1 for text
6. WHEN form validation fails, THE Admin_Dashboard SHALL announce errors to screen readers
