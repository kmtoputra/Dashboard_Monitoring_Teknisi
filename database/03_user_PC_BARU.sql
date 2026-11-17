USE gpi_monitoring_system;

CREATE USER IF NOT EXISTS 'gpi_ingest'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
ALTER USER 'gpi_ingest'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
GRANT SELECT, INSERT, UPDATE ON gpi_monitoring_system.* TO 'gpi_ingest'@'localhost';

CREATE USER IF NOT EXISTS 'gpi_dashboard'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
ALTER USER 'gpi_dashboard'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
GRANT SELECT, INSERT, UPDATE ON gpi_monitoring_system.* TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.telemetri      TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.agregat_1menit TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.riwayat_status TO 'gpi_dashboard'@'localhost';
GRANT SHOW VIEW, LOCK TABLES ON gpi_monitoring_system.* TO 'gpi_dashboard'@'localhost';

CREATE USER IF NOT EXISTS 'gpi_viewer'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
GRANT SELECT ON gpi_monitoring_system.* TO 'gpi_viewer'@'localhost';

CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_status_terkini AS
SELECT l.kode       AS lokasi,
       l.nama_rs,
       l.kota,
       m.id         AS mesin_id,
       m.nama       AS mesin,
       t.waktu,
       TIMESTAMPDIFF(SECOND, t.waktu, NOW()) AS detik_sejak_data,
       t.avgpur, t.ae1, t.ae_1, t.ps1, t.state, t.vsacmd, t.vsaalm,
       t.flow_est, t.purgeest, t.cyccnt, t.controller
FROM mesin m
JOIN lokasi l   ON l.id = m.lokasi_id
JOIN sesi_log s ON s.id = (SELECT s2.id FROM sesi_log s2
                           WHERE s2.mesin_id = m.id
                           ORDER BY s2.waktu_terakhir DESC
                           LIMIT 1)
JOIN telemetri t ON t.sesi_id = s.id AND t.rec_no = s.rec_no_terakhir;

SELECT user, host FROM mysql.user WHERE user LIKE 'gpi\_%' ORDER BY user;
SELECT (SELECT COUNT(*) FROM telemetri)  AS baris_telemetri,
       (SELECT COUNT(*) FROM mesin)      AS unit,
       (SELECT COUNT(*) FROM pengguna)   AS akun_dashboard,
       (SELECT COUNT(*) FROM aturan_alarm) AS aturan_alarm,
       (SELECT MAX(waktu) FROM telemetri) AS data_terakhir;
