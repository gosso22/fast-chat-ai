# Implementation Plan: Admin Dashboard

## Overview

This plan implements a frontend-only Admin Dashboard for managing environments and user roles. The implementation follows a mobile-first responsive approach using React 19, TypeScript, and Tailwind CSS v4. Backend APIs at `/api/environments` and `/api/roles` are already implemented.

## Tasks

- [ ] 1. Set up shared UI components and infrastructure
  - [x] 1.1 Create TypeScript types for admin entities
    - Create `frontend/src/types/admin.ts` with Environment, UserRole, and related interfaces
    - Export types from `frontend/src/types/index.ts`
    - _Requirements: 2.2, 6.2_

  - [x] 1.2 Create LoadingSpinner component
    - Create `frontend/src/components/ui/LoadingSpinner.tsx` with size variants (sm, md, lg)
    - Use Tailwind CSS for spinner animation
    - _Requirements: 11.1_

  - [x] 1.3 Create EmptyState component
    - Create `frontend/src/components/ui/EmptyState.tsx` with icon, title, description, and optional action
    - _Requirements: 2.6, 6.7_

  - [x] 1.4 Create Modal component
    - Create `frontend/src/components/ui/Modal.tsx` as base modal with focus trap
    - Full-screen on mobile, centered dialog on desktop
    - Support keyboard navigation (Escape to close)
    - _Requirements: 10.5, 12.3, 12.4_

  - [x] 1.5 Create ConfirmDialog component
    - Create `frontend/src/components/ui/ConfirmDialog.tsx` using Modal
    - Support danger/warning variants, loading state
    - _Requirements: 5.2, 5.3, 9.2, 9.3_

  - [x] 1.6 Create Toast notification system
    - Create `frontend/src/components/ui/Toast.tsx` for individual toast
    - Create `frontend/src/components/ui/ToastProvider.tsx` with context
    - Create `frontend/src/hooks/useToast.ts` hook
    - Auto-dismiss success (5s), persistent errors, responsive positioning
    - _Requirements: 11.4, 11.5, 11.6_

  - [x] 1.7 Write unit tests for shared UI components
    - Test Modal focus trap and keyboard navigation
    - Test ConfirmDialog confirm/cancel actions
    - Test Toast auto-dismiss and manual dismiss
    - _Requirements: 12.4_

- [ ] 2. Checkpoint - Ensure shared UI components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Implement API client modules
  - [ ] 3.1 Create environments API client
    - Create `frontend/src/api/environments.ts` with list, get, create, update, delete methods
    - Use existing apiClient from `frontend/src/api/client.ts`
    - _Requirements: 2.1, 3.5, 4.3, 5.4_

  - [ ] 3.2 Create roles API client
    - Create `frontend/src/api/roles.ts` with list (with filters), get, create, update, delete methods
    - Support environment_id and user_id query parameters for filtering
    - _Requirements: 6.1, 7.5, 8.4, 9.4_

  - [ ]* 3.3 Write unit tests for API clients
    - Test API calls with correct endpoints and parameters
    - Test error handling for various HTTP status codes
    - _Requirements: 11.3_

- [ ] 4. Implement Environment management components
  - [ ] 4.1 Create EnvironmentCard component
    - Create `frontend/src/components/admin/EnvironmentCard.tsx` for mobile card view
    - Display name, description, created_by, created_at, document count
    - Include edit and delete action buttons with 44px touch targets
    - _Requirements: 2.2, 2.3, 2.7, 4.1, 5.1, 10.4_

  - [ ] 4.2 Create EnvironmentList component
    - Create `frontend/src/components/admin/EnvironmentList.tsx`
    - Table view on desktop (lg:), card view on mobile
    - Handle loading, error, and empty states
    - Include "Create Environment" button
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 3.1_

  - [ ]* 4.3 Write property test for EnvironmentList required information
    - **Property 1: Environment list displays all required information**
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 4.4 Write property test for EnvironmentList required actions
    - **Property 2: Environment list displays all required actions**
    - **Validates: Requirements 4.1, 5.1**

  - [ ] 4.5 Create EnvironmentForm component
    - Create `frontend/src/components/admin/EnvironmentForm.tsx`
    - Support create and edit modes
    - Validate name (required, 1-255 chars)
    - Handle 409 conflict errors inline
    - _Requirements: 3.2, 3.3, 3.4, 3.6, 3.7, 3.8, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.6 Write property test for EnvironmentForm validation
    - **Property 3: Environment name validation rejects invalid input**
    - **Validates: Requirements 3.4**

  - [ ]* 4.7 Write unit tests for Environment components
    - Test EnvironmentList loading, error, empty states
    - Test EnvironmentForm validation and submission
    - _Requirements: 2.4, 2.5, 2.6, 3.4_

- [ ] 5. Checkpoint - Ensure environment components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement Role management components
  - [ ] 6.1 Create RoleCard component
    - Create `frontend/src/components/admin/RoleCard.tsx` for mobile card view
    - Display user_id, role type, environment name, created_at
    - Include edit and delete action buttons with 44px touch targets
    - _Requirements: 6.2, 6.8, 8.1, 9.1, 10.4_

  - [ ] 6.2 Create RoleFilters component
    - Create `frontend/src/components/admin/RoleFilters.tsx`
    - Environment dropdown filter and user_id search input
    - _Requirements: 6.3, 6.4_

  - [ ] 6.3 Create RoleList component
    - Create `frontend/src/components/admin/RoleList.tsx`
    - Table view on desktop (lg:), card view on mobile
    - Handle loading, error, and empty states
    - Include filters and "Assign Role" button
    - _Requirements: 6.1, 6.5, 6.6, 6.7, 7.1_

  - [ ]* 6.4 Write property test for RoleList required information
    - **Property 4: Role list displays all required information**
    - **Validates: Requirements 6.2**

  - [ ]* 6.5 Write property test for RoleList environment filter
    - **Property 5: Role list environment filter returns correct results**
    - **Validates: Requirements 6.3**

  - [ ]* 6.6 Write property test for RoleList user filter
    - **Property 6: Role list user filter returns correct results**
    - **Validates: Requirements 6.4**

  - [ ]* 6.7 Write property test for RoleList required actions
    - **Property 7: Role list displays all required actions**
    - **Validates: Requirements 8.1, 9.1**

  - [ ] 6.8 Create RoleForm component
    - Create `frontend/src/components/admin/RoleForm.tsx`
    - Support create and edit modes
    - In edit mode, only role type is editable
    - Validate all required fields
    - Handle 409 and 404 errors inline
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 6.9 Write property test for RoleForm validation
    - **Property 8: Role form validation rejects incomplete input**
    - **Validates: Requirements 7.4**

  - [ ]* 6.10 Write unit tests for Role components
    - Test RoleList loading, error, empty states, filtering
    - Test RoleForm validation and submission modes
    - _Requirements: 6.5, 6.6, 6.7, 7.4_

- [ ] 7. Checkpoint - Ensure role components work
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement AdminPage and navigation
  - [ ] 8.1 Create AdminPage component
    - Create `frontend/src/pages/AdminPage.tsx`
    - Tabbed interface with Environments and Roles sections
    - Integrate EnvironmentList, RoleList, forms, and dialogs
    - Wire up toast notifications for CRUD operations
    - _Requirements: 1.3, 3.6, 4.4, 5.5, 5.6, 7.6, 8.5, 9.5_

  - [ ] 8.2 Update navigation with Admin link
    - Add "Admin" link to header navigation
    - Implement mobile hamburger menu for viewport < 768px
    - _Requirements: 1.1, 1.4, 1.5_

  - [ ] 8.3 Add /admin route to router
    - Update `frontend/src/router.tsx` with /admin route
    - _Requirements: 1.2_

  - [ ] 8.4 Create admin component barrel export
    - Create `frontend/src/components/admin/index.ts`
    - Create `frontend/src/components/ui/index.ts`
    - _Requirements: N/A (code organization)_

  - [ ]* 8.5 Write unit tests for AdminPage
    - Test tab switching between Environments and Roles
    - Test CRUD operation flows with toast notifications
    - _Requirements: 1.3_

- [ ] 9. Implement accessibility and responsive polish
  - [ ] 9.1 Add ARIA labels and semantic HTML
    - Ensure all interactive elements have accessible names
    - Use semantic elements (nav, main, section, button, form)
    - Add aria-labels where text content is insufficient
    - _Requirements: 12.1, 12.2_

  - [ ] 9.2 Implement keyboard navigation
    - Ensure all interactive elements are focusable
    - Support Tab navigation through all controls
    - _Requirements: 12.3_

  - [ ] 9.3 Add form error announcements
    - Announce validation errors to screen readers using aria-live
    - _Requirements: 12.6_

  - [ ]* 9.4 Write property test for touch target sizes
    - **Property 9: Interactive elements meet minimum touch target size**
    - **Validates: Requirements 10.4**

  - [ ]* 9.5 Write property test for loading states
    - **Property 10: API operations display appropriate loading states**
    - **Validates: Requirements 11.1, 11.2**

  - [ ]* 9.6 Write property test for error messages
    - **Property 11: API failures display user-friendly error messages**
    - **Validates: Requirements 11.3**

  - [ ]* 9.7 Write property test for accessibility
    - **Property 12: Interactive elements are accessible**
    - **Validates: Requirements 12.1, 12.2, 12.3**

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests use fast-check library with minimum 100 iterations
- Backend APIs are already implemented; this is frontend-only work
