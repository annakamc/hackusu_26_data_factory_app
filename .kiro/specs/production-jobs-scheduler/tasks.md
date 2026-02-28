# Implementation Plan: Production Jobs Scheduler

## Overview

This plan implements a standalone Python daemon for automated job scheduling with cron-based execution. The implementation follows a modular architecture with five core components: ConfigLoader, JobExecutor, JobLogger, JobScheduler, and CLI. The system uses the `schedule` library for scheduling, `subprocess` for command execution, and `hypothesis` for property-based testing.

## Tasks

- [ ] 1. Set up project structure and dependencies
  - Create `production_jobs/` directory with `__init__.py`
  - Create `production_jobs/jobs/` directory for job definitions
  - Create `logs/` directory for log files
  - Add required dependencies: `schedule`, `hypothesis` (for testing)
  - _Requirements: 5.1, 5.2_

- [ ] 2. Implement data models and configuration loader
  - [ ] 2.1 Create JobConfig data class with validation
    - Implement `JobConfig` class with fields: name, schedule, command, working_directory, enabled
    - Implement `validate_cron()` method to validate 5-field cron expressions
    - _Requirements: 1.2, 1.3, 2.2, 2.3_
  
  - [ ]* 2.2 Write property test for JobConfig round-trip
    - **Property 1: Job Configuration Round-Trip**
    - **Validates: Requirements 1.2**
  
  - [ ]* 2.3 Write property test for required fields validation
    - **Property 3: Required Fields Validation**
    - **Validates: Requirements 1.3**
  
  - [ ] 2.4 Implement ConfigLoader class
    - Implement `__init__()` to accept jobs directory path
    - Implement `load_all_jobs()` to scan directory and load all JSON files
    - Implement `_parse_job_file()` to parse single JSON file with error handling
    - Handle invalid JSON gracefully with logging
    - _Requirements: 1.1, 1.2, 1.4, 1.5_
  
  - [ ]* 2.5 Write property test for multiple job files loading
    - **Property 2: Multiple Job Files Loading**
    - **Validates: Requirements 1.1, 1.5**
  
  - [ ]* 2.6 Write property test for invalid JSON rejection
    - **Property 4: Invalid JSON Rejection**
    - **Validates: Requirements 1.4**
  
  - [ ]* 2.7 Write property test for cron expression validation
    - **Property 5: Cron Expression Validation**
    - **Validates: Requirements 2.2, 2.3, 2.4**
  
  - [ ]* 2.8 Write unit tests for ConfigLoader edge cases
    - Test empty jobs directory
    - Test non-existent jobs directory
    - Test malformed JSON files
    - _Requirements: 1.4_

- [ ] 3. Checkpoint - Verify configuration loading
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement job execution engine
  - [ ] 4.1 Create JobResult data class
    - Implement `JobResult` class with fields: job_name, start_time, end_time, exit_code, stdout, stderr, duration_seconds
    - Implement `success` property to check if exit_code is 0
    - _Requirements: 3.3, 3.4_
  
  - [ ] 4.2 Implement JobExecutor class
    - Implement `execute()` method to run job and return JobResult
    - Implement `_run_command()` using `subprocess.run()` with timeout
    - Capture stdout and stderr streams
    - Record start time, end time, and duration
    - Set working directory from job config
    - Handle command failures gracefully
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  
  - [ ]* 4.3 Write property test for working directory execution
    - **Property 6: Working Directory Execution**
    - **Validates: Requirements 3.2**
  
  - [ ]* 4.4 Write property test for output capture completeness
    - **Property 7: Output Capture Completeness**
    - **Validates: Requirements 3.3**
  
  - [ ]* 4.5 Write property test for exit code recording
    - **Property 8: Exit Code Recording**
    - **Validates: Requirements 3.4**
  
  - [ ]* 4.6 Write unit tests for JobExecutor edge cases
    - Test command with no output
    - Test command with large output
    - Test command not found error
    - Test working directory doesn't exist error
    - Test command timeout
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 5. Implement logging system
  - [ ] 5.1 Create JobLogger class with rotating file handlers
    - Implement `__init__()` to set up two loggers: main scheduler and job execution
    - Configure `RotatingFileHandler` with 10MB max size and 5 backups
    - Set up log format with timestamp, level, component, and message
    - Create log files: `scheduler_main.log` and `scheduler_jobs.log`
    - _Requirements: 4.3, 4.5_
  
  - [ ] 5.2 Implement logging methods
    - Implement `log_startup()` for scheduler start events
    - Implement `log_shutdown()` for scheduler stop events
    - Implement `log_job_start()` for job execution start
    - Implement `log_job_complete()` for job execution completion with full details
    - Implement `log_config_error()` for configuration parsing errors
    - Implement `log_schedule_error()` for scheduling errors
    - _Requirements: 4.1, 4.2, 4.4, 5.4, 5.5_
  
  - [ ]* 5.3 Write property test for job execution logging completeness
    - **Property 10: Job Execution Logging Completeness**
    - **Validates: Requirements 4.1, 4.2, 4.4**
  
  - [ ]* 5.4 Write property test for log file creation
    - **Property 11: Log File Creation**
    - **Validates: Requirements 4.3**
  
  - [ ]* 5.5 Write property test for log rotation behavior
    - **Property 12: Log Rotation Behavior**
    - **Validates: Requirements 4.5**
  
  - [ ]* 5.6 Write property test for lifecycle event logging
    - **Property 13: Lifecycle Event Logging**
    - **Validates: Requirements 5.4**
  
  - [ ]* 5.7 Write unit tests for logging edge cases
    - Test log entry with special characters in output
    - Test log directory not writable error
    - _Requirements: 4.3_

- [ ] 6. Checkpoint - Verify execution and logging
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement core scheduler logic
  - [ ] 7.1 Create JobScheduler class
    - Implement `__init__()` to initialize ConfigLoader, JobExecutor, and JobLogger
    - Store jobs directory and log directory paths
    - Initialize shutdown flag for graceful termination
    - _Requirements: 5.1, 5.2_
  
  - [ ] 7.2 Implement job registration and scheduling
    - Implement `_register_jobs()` to register jobs with `schedule` library
    - Parse cron expressions and convert to schedule library format
    - Skip disabled jobs (enabled=false)
    - Log scheduling errors for invalid cron expressions
    - _Requirements: 2.1, 2.3, 2.4, 3.5_
  
  - [ ]* 7.3 Write property test for disabled jobs exclusion
    - **Property 9: Disabled Jobs Exclusion**
    - **Validates: Requirements 3.5**
  
  - [ ] 7.4 Implement job execution wrapper
    - Implement `_execute_job_wrapper()` to wrap JobExecutor.execute()
    - Log job start before execution
    - Log job completion after execution with full results
    - Handle execution errors gracefully
    - _Requirements: 3.1, 4.1, 4.2_
  
  - [ ] 7.5 Implement scheduler main loop
    - Implement `_run_scheduler_loop()` to continuously check for pending jobs
    - Use `schedule.run_pending()` to execute scheduled jobs
    - Check shutdown flag on each iteration
    - Sleep 1 second between checks
    - _Requirements: 2.5, 5.2_
  
  - [ ] 7.6 Implement graceful shutdown
    - Implement `shutdown()` method to set shutdown flag
    - Wait for currently running job to complete
    - Log shutdown event
    - _Requirements: 5.3, 5.4_
  
  - [ ] 7.7 Implement signal handlers
    - Register SIGTERM and SIGINT handlers
    - Call `shutdown()` when signals received
    - _Requirements: 5.3_
  
  - [ ] 7.8 Implement start method
    - Implement `start()` to orchestrate scheduler startup
    - Load job configurations using ConfigLoader
    - Register jobs with scheduler
    - Log startup event with job count
    - Enter main scheduler loop
    - _Requirements: 5.1, 5.4_
  
  - [ ]* 7.9 Write property test for error logging before termination
    - **Property 14: Error Logging Before Termination**
    - **Validates: Requirements 5.5**
  
  - [ ]* 7.10 Write unit tests for scheduler edge cases
    - Test scheduler with no jobs
    - Test scheduler with all disabled jobs
    - Test graceful shutdown with running job
    - Test signal handling
    - _Requirements: 5.3, 5.4_

- [ ] 8. Implement CLI entry point
  - [ ] 8.1 Create scheduler_cli.py with command-line interface
    - Implement `main()` function to parse command-line arguments
    - Support "start" command to start the scheduler
    - Validate command-line arguments
    - Provide clear error messages for invalid usage
    - Return appropriate exit codes
    - _Requirements: 5.1_
  
  - [ ] 8.2 Wire CLI to JobScheduler
    - Instantiate JobScheduler with correct paths
    - Call `scheduler.start()` when "start" command is used
    - Handle exceptions and log errors before exit
    - _Requirements: 5.1, 5.5_
  
  - [ ]* 8.3 Write unit tests for CLI
    - Test valid "start" command
    - Test invalid command arguments
    - Test error handling
    - _Requirements: 5.1_

- [ ] 9. Implement Job Management Service
  - [ ] 9.1 Create JobManagementService class with initialization
    - Implement `__init__()` to accept jobs_directory and log_directory paths
    - Initialize ConfigLoader, JobExecutor, and JobLogger instances
    - _Requirements: 7.2, 7.3_
  
  - [ ] 9.2 Implement job listing and retrieval methods
    - Implement `list_jobs()` to return all job configurations
    - Implement `get_job_history()` to parse log files and return execution history
    - Implement `get_job_logs()` to extract log entries for specific job
    - _Requirements: 7.2, 7.3, 7.6_
  
  - [ ] 9.3 Implement job CRUD operations
    - Implement `create_job()` to write new job configuration file
    - Implement `update_job()` to modify existing job configuration file
    - Implement `delete_job()` to remove job configuration file
    - Add validation for all inputs before file operations
    - Raise appropriate exceptions (JobNotFoundError, JobAlreadyExistsError, ValidationError)
    - _Requirements: 7.7, 7.8, 7.12_
  
  - [ ] 9.4 Implement job control operations
    - Implement `enable_job()` to set enabled=true in job config
    - Implement `disable_job()` to set enabled=false in job config
    - Implement `trigger_job()` to manually execute a job immediately
    - _Requirements: 7.4, 7.5_
  
  - [ ]* 9.5 Write property test for CRUD round-trip
    - **Property 15: Job Management Service CRUD Operations**
    - **Validates: Requirements 7.7, 7.8**
  
  - [ ]* 9.6 Write property test for enable/disable toggle
    - **Property 16: Job Enable/Disable Toggle**
    - **Validates: Requirements 7.4**
  
  - [ ]* 9.7 Write property test for manual job trigger
    - **Property 17: Manual Job Trigger Execution**
    - **Validates: Requirements 7.5**
  
  - [ ]* 9.8 Write property test for job history retrieval
    - **Property 18: Job History Retrieval**
    - **Validates: Requirements 7.3**
  
  - [ ]* 9.9 Write property test for log filtering
    - **Property 19: Log Filtering**
    - **Validates: Requirements 7.6**
  
  - [ ]* 9.10 Write unit tests for service edge cases
    - Test create job with duplicate name
    - Test update non-existent job
    - Test delete non-existent job
    - Test trigger disabled job
    - Test concurrent file modifications
    - _Requirements: 7.7, 7.8_

- [ ] 10. Checkpoint - Verify job management service
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement Gradio UI components for job management
  - [ ] 11.1 Create jobs_section accordion in admin_tab.py
    - Add `create_jobs_section()` function that returns gr.Accordion
    - Initialize JobManagementService instance
    - Set up accordion to be collapsed by default
    - _Requirements: 7.1, 7.10_
  
  - [ ] 11.2 Implement job list table UI
    - Create Gradio DataFrame component for job list
    - Add columns: name, status, schedule, last_run, next_run, enabled
    - Add "Refresh Jobs" button
    - Implement `on_refresh_jobs()` handler with auth check
    - _Requirements: 7.1, 7.2_
  
  - [ ] 11.3 Implement job action buttons
    - Add "Enable", "Disable", "Trigger Now", and "Delete" buttons
    - Implement `on_enable_job()` handler with auth check and audit logging
    - Implement `on_disable_job()` handler with auth check and audit logging
    - Implement `on_trigger_job()` handler with auth check and audit logging
    - Implement `on_delete_job()` handler with confirmation dialog, auth check, and audit logging
    - _Requirements: 7.4, 7.5, 7.9, 7.14_
  
  - [ ] 11.4 Implement job creation form
    - Create tab with form inputs: name, schedule, command, working_directory, enabled
    - Add cron expression helper text with examples
    - Implement `on_create_job()` handler with validation, auth check, and audit logging
    - Add field-level validation for cron expressions
    - Display success/error messages
    - _Requirements: 7.7, 7.9, 7.12_
  
  - [ ] 11.5 Implement job editing form
    - Create tab with job selector dropdown and form inputs
    - Pre-populate form when job is selected
    - Make job name read-only in edit mode
    - Implement `on_update_job()` handler with validation, auth check, and audit logging
    - Add field-level validation for cron expressions
    - Display success/error messages
    - _Requirements: 7.8, 7.9, 7.12_
  
  - [ ] 11.6 Implement job history viewer
    - Create section with job selector dropdown
    - Add filter controls for date range and status
    - Create Gradio DataFrame for history table with columns: timestamp, status, duration, exit_code
    - Implement `on_view_history()` handler with auth check and audit logging
    - Add "Refresh" button
    - _Requirements: 7.3, 7.9, 7.13_
  
  - [ ] 11.7 Implement log viewer with filtering
    - Create section with job selector dropdown
    - Add search input and status filter dropdown
    - Create scrollable text area for log display
    - Implement `on_view_logs()` handler with filtering, auth check, and audit logging
    - Add "Refresh" and "Download Logs" buttons
    - _Requirements: 7.6, 7.9_
  
  - [ ] 11.8 Wire all UI components together
    - Connect all event handlers to UI components
    - Set up component visibility and state management
    - Add loading indicators for async operations
    - Implement error message display
    - _Requirements: 7.1, 7.10_
  
  - [ ]* 11.9 Write property test for admin authorization enforcement
    - **Property 20: Admin Authorization Enforcement**
    - **Validates: Requirements 7.1, 7.11**
  
  - [ ]* 11.10 Write property test for audit logging completeness
    - **Property 21: Audit Logging Completeness**
    - **Validates: Requirements 7.9**
  
  - [ ]* 11.11 Write unit tests for UI edge cases
    - Test non-admin user access attempt
    - Test invalid form input handling
    - Test job not found error handling
    - Test concurrent modification handling
    - Test confirmation dialog for delete action
    - _Requirements: 7.11, 7.14_

- [ ] 12. Create example job configuration and documentation
  - [ ] 12.1 Create example job definition file
    - Create `production_jobs/jobs/example_job.json`
    - Include all required fields with example values
    - Add comments explaining each field (in separate README)
    - Use valid daily cron expression
    - Set enabled to false by default
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  
  - [ ] 12.2 Create README.md documentation
    - Document job configuration schema
    - Explain cron expression format with examples
    - Provide usage instructions for starting scheduler
    - Document log file locations and formats
    - Include troubleshooting guide
    - Document UI usage for job management
    - _Requirements: 6.2, 6.3_

- [ ] 13. Final checkpoint - Integration testing
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` library with minimum 100 iterations
- All property tests include feature and property tags in comments
- The scheduler runs as an independent process from the main Gradio application
- The Gradio UI provides admin-only access to job management through the admin tab
- All UI operations require admin role verification and are audit logged
- Job Management Service provides the bridge between UI and scheduler components
- Graceful shutdown ensures running jobs complete before termination
- Log rotation prevents unbounded disk usage
