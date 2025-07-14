# Database Migration Plan for User Libraries

This document outlines the high-level architectural plan for migrating user library data from the current local JSON file (`user_libraries.json`) to a more robust, secure, and scalable SQL database.

## 1. Database Choice

*   **Options:**
    *   **PostgreSQL:** A powerful, open-source, and highly extensible object-relational database system known for its strong adherence to SQL standards, data integrity, and advanced features. Excellent for general-purpose applications requiring reliability and scalability.
    *   **MySQL:** Another popular open-source relational database, widely used for web applications. Known for its performance, ease of use, and large community support.
    *   **SQLite:** A self-contained, serverless, zero-configuration, transactional SQL database engine. Ideal for simpler cases, embedded applications, or when a full-fledged database server is overkill (e.g., a single-instance bot without extreme concurrency needs).
*   **Why they are better:** SQL databases provide ACID (Atomicity, Consistency, Isolation, Durability) properties, ensuring data integrity. They offer robust concurrency control, indexing for fast queries, built-in security features (user roles, permissions), and mature backup/recovery mechanisms.

## 2. Authentication/Authorization Integration

*   **User Management System:**
    *   A dedicated `Users` table would store user credentials (hashed passwords), unique user IDs, and other relevant user information.
    *   User authentication would involve verifying credentials against this table.
    *   Authorization would be managed by linking user IDs to their respective libraries. Each library record would have a foreign key referencing the `Users` table, ensuring that only the owning user (or an authorized administrator) can access or modify their libraries.
    *   This centralizes user management, making it more secure and auditable.

## 3. Data Model

*   **Tables:**
    *   **`Users` Table:**
        *   `user_id` (Primary Key, e.g., UUID or auto-incrementing integer)
        *   `username` (Unique, e.g., Telegram user ID or a custom username)
        *   `password_hash` (For custom authentication, if applicable)
        *   `created_at`
        *   `last_login`
        *   ... (other user-specific metadata)
    *   **`Libraries` Table:**
        *   `library_id` (Primary Key)
        *   `user_id` (Foreign Key referencing `Users.user_id`)
        *   `library_name` (e.g., "My Favorites", "Reading List")
        *   `created_at`
        *   `updated_at`
        *   ... (other library-specific metadata)
    *   **`LibraryItems` Table (or `NovelsInLibraries`):**
        *   `library_item_id` (Primary Key)
        *   `library_id` (Foreign Key referencing `Libraries.library_id`)
        *   `novel_id` (Foreign Key referencing a `Novels` table, if novels are also stored in the DB, or a unique identifier for the novel)
        *   `added_at`
        *   `read_progress` (e.g., last chapter read)
        *   ... (other item-specific metadata)

*   **Relationship:** A `User` can have multiple `Libraries`, and each `Library` can contain multiple `LibraryItems` (novels). This is a one-to-many relationship between `Users` and `Libraries`, and a many-to-many relationship between `Libraries` and `Novels` (resolved by the `LibraryItems` junction table).

## 4. Migration Strategy

1.  **Schema Definition:** Define the SQL schema for the `Users`, `Libraries`, and `LibraryItems` tables.
2.  **Database Setup:** Set up the chosen SQL database (e.g., install PostgreSQL, create a database, define users/permissions).
3.  **Data Extraction:** Read the existing `user_libraries.json` file into memory.
4.  **Data Transformation:** Parse the JSON data and transform it to fit the new relational schema. This will involve mapping existing JSON structures to rows in the `Users`, `Libraries`, and `LibraryItems` tables. Generate unique IDs for new records.
5.  **Data Loading:** Insert the transformed data into the new SQL database tables. This can be done via a script.
6.  **Application Update:** Modify the application code to interact with the SQL database using an ORM (Object-Relational Mapper) or a database connector library (e.g., SQLAlchemy for Python) instead of reading/writing JSON files.
7.  **Testing:** Thoroughly test the new database integration to ensure all functionalities work correctly and data integrity is maintained.
8.  **Cutover:** Once confident, switch the production environment to use the new database.

## 5. Benefits

*   **Enhanced Security:**
    *   **Access Control:** Granular permissions at the database level, controlled by user roles and privileges.
    *   **Encryption:** Support for encryption at rest (database-level encryption) and in transit (SSL/TLS connections).
    *   **Data Integrity:** ACID properties, transactions, and foreign key constraints prevent data corruption and ensure consistency.
    *   **Auditing:** Most databases offer robust logging and auditing capabilities.
*   **Improved Scalability:**
    *   **Performance:** Optimized queries with indexing, efficient data retrieval, and caching mechanisms.
    *   **Concurrency:** Robust locking mechanisms handle simultaneous read/write operations without data loss.
    *   **Deployment:** Easily deployable in distributed environments, supporting replication, sharding, and load balancing for horizontal scaling.
    *   **Query Capabilities:** Full SQL query language support for complex data analysis and reporting.
*   **Maintainability & Features:** Easier to manage, backup, restore, and extend. Supports complex relationships and provides a foundation for future features like search, reporting, and advanced user management.