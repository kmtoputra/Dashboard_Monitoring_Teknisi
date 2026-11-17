CREATE DATABASE IF NOT EXISTS gpi_monitoring_system CHARACTER SET utf8mb4;
USE gpi_monitoring_system;

CREATE TABLE IF NOT EXISTS lokasi (
  id            SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  kode          VARCHAR(20)  NOT NULL UNIQUE,
  nama_rs       VARCHAR(100) NULL,
  kota          VARCHAR(60)  NOT NULL,
  provinsi      VARCHAR(60)  NOT NULL,
  subnet_router VARCHAR(18)  NULL,
  aktif         TINYINT(1)   NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mesin (
  id         SMALLINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  lokasi_id  SMALLINT UNSIGNED NOT NULL,
  nama       VARCHAR(50)  NOT NULL,
  ip_kantor  VARCHAR(15)  NULL,
  mac        CHAR(17)     NULL,
  aktif      TINYINT(1)   NOT NULL DEFAULT 1,
  FOREIGN KEY (lokasi_id) REFERENCES lokasi(id)
);

SET @ada := (SELECT COUNT(*) FROM information_schema.COLUMNS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'mesin' AND COLUMN_NAME = 'pola_workbook');
SET @sql := IF(@ada = 0, 'ALTER TABLE mesin ADD COLUMN pola_workbook VARCHAR(200) NULL AFTER mac', 'DO 0');
PREPARE s FROM @sql; EXECUTE s; DEALLOCATE PREPARE s;

CREATE TABLE IF NOT EXISTS sesi_log (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  mesin_id         SMALLINT UNSIGNED NOT NULL,
  waktu_mulai      DATETIME     NOT NULL,
  detik_unit_mulai INT UNSIGNED NOT NULL,
  nama_sumber      VARCHAR(255) NULL,
  rec_no_terakhir  INT UNSIGNED NOT NULL DEFAULT 0,
  waktu_terakhir   DATETIME     NULL,
  dibuat           TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  diperbarui       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_sesi (mesin_id, waktu_mulai, detik_unit_mulai),
  KEY ix_mesin_terakhir (mesin_id, waktu_terakhir),
  FOREIGN KEY (mesin_id) REFERENCES mesin(id)
);

CREATE TABLE IF NOT EXISTS telemetri (
  sesi_id     INT UNSIGNED      NOT NULL,
  rec_no      INT UNSIGNED      NOT NULL,
  mesin_id    SMALLINT UNSIGNED NOT NULL,
  waktu       DATETIME          NOT NULL,
  detik_unit  INT UNSIGNED      NULL,
  ae1         DECIMAL(8,2) NULL,
  avgpur      DECIMAL(8,2) NULL,
  xt_1        DECIMAL(8,2) NULL,
  xt_2        DECIMAL(8,2) NULL,
  xt_3        DECIMAL(8,2) NULL,
  xt_4        DECIMAL(8,2) NULL,
  xt_5        DECIMAL(8,2) NULL,
  ae_1        DECIMAL(8,2) NULL,
  svx         DECIMAL(8,2) NULL,
  tba1        DECIMAL(8,2) NULL,
  tba2        DECIMAL(8,2) NULL,
  tba3        DECIMAL(8,2) NULL,
  tba4        DECIMAL(8,2) NULL,
  tba5        DECIMAL(8,2) NULL,
  ps1         DECIMAL(8,2) NULL,
  cyccnt      INT UNSIGNED NULL,
  sv_1        VARCHAR(12)  NULL,
  sv_2        VARCHAR(12)  NULL,
  sv_3        VARCHAR(12)  NULL,
  sv_4        VARCHAR(12)  NULL,
  sv_5        VARCHAR(12)  NULL,
  sv_6        VARCHAR(12)  NULL,
  rtd_1       DECIMAL(8,2) NULL,
  rtd_2       DECIMAL(8,2) NULL,
  rtd_3       DECIMAL(8,2) NULL,
  rtd_4       DECIMAL(8,2) NULL,
  rtd_5       DECIMAL(8,2) NULL,
  rtd_6       DECIMAL(8,2) NULL,
  rtd_7       DECIMAL(8,2) NULL,
  rtd_8       DECIMAL(8,2) NULL,
  controller  DECIMAL(8,2) NULL,
  vsacmd      VARCHAR(12)  NULL,
  vsaalm      VARCHAR(12)  NULL,
  fvsa        DECIMAL(8,2) NULL,
  bstcmd      VARCHAR(12)  NULL,
  bstalm      VARCHAR(12)  NULL,
  fbst        DECIMAL(8,2) NULL,
  state       VARCHAR(12)  NULL,
  dwncnt      VARCHAR(12)  NULL,
  buffmin     DECIMAL(8,2) NULL,
  buffmax     DECIMAL(8,2) NULL,
  cycledur    DECIMAL(8,2) NULL,
  flow_est    DECIMAL(8,2) NULL,
  purgeest    DECIMAL(8,2) NULL,
  lainnya     JSON         NULL,
  masuk       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (sesi_id, rec_no),
  KEY ix_mesin_waktu (mesin_id, waktu)
);

INSERT IGNORE INTO lokasi (kode, nama_rs, kota, provinsi, subnet_router) VALUES
('BANDUNG',  'RS Contoh Bandung', 'Bandung',  'Jawa Barat',          '192.168.100.0/24'),
('SEMARANG', NULL,                'Semarang', 'Jawa Tengah',         '192.168.101.0/24'),
('MANADO',   NULL,                'Manado',   'Sulawesi Utara',      NULL),
('MALANG',   NULL,                'Malang',   'Jawa Timur',          NULL),
('PADANG',   NULL,                'Padang',   'Sumatera Barat',      NULL),
('KUPANG',   NULL,                'Kupang',   'Nusa Tenggara Timur', NULL),
('MATARAM',  NULL,                'Mataram',  'Nusa Tenggara Barat', NULL),
('JAMBI',    NULL,                'Jambi',    'Jambi',               NULL);

INSERT INTO mesin (lokasi_id, nama, ip_kantor, mac, pola_workbook)
SELECT l.id, 'DOCS500', '192.168.100.20', '00:00:00:00:00:01', 'Bandung'
FROM lokasi l WHERE l.kode = 'BANDUNG'
  AND NOT EXISTS (SELECT 1 FROM mesin m WHERE m.lokasi_id = l.id AND m.nama = 'DOCS500');

INSERT INTO mesin (lokasi_id, nama, ip_kantor, mac, pola_workbook)
SELECT l.id, 'DOCS500', '192.168.101.20', '00:00:00:00:00:02', 'Semarang'
FROM lokasi l WHERE l.kode = 'SEMARANG'
  AND NOT EXISTS (SELECT 1 FROM mesin m WHERE m.lokasi_id = l.id AND m.nama = 'DOCS500');

UPDATE mesin m JOIN lokasi l ON l.id = m.lokasi_id
SET m.pola_workbook = 'Bandung'
WHERE l.kode = 'BANDUNG' AND m.nama = 'DOCS500' AND m.pola_workbook IS NULL;
UPDATE mesin m JOIN lokasi l ON l.id = m.lokasi_id
SET m.pola_workbook = 'Semarang'
WHERE l.kode = 'SEMARANG' AND m.nama = 'DOCS500' AND m.pola_workbook IS NULL;

CREATE OR REPLACE VIEW v_status_terkini AS
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

SELECT l.kode, m.id AS mesin_id, m.nama, m.ip_kantor, m.pola_workbook
FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id ORDER BY l.kode;
