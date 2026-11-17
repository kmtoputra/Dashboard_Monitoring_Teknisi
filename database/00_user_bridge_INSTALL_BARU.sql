CREATE USER IF NOT EXISTS 'gpi_ingest'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
GRANT SELECT, INSERT, UPDATE ON gpi_monitoring_system.* TO 'gpi_ingest'@'localhost';
SHOW GRANTS FOR 'gpi_ingest'@'localhost';
