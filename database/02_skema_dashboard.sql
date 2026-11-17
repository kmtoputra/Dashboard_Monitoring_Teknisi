USE gpi_monitoring_system;

DROP PROCEDURE IF EXISTS _tambah_kolom;
DROP PROCEDURE IF EXISTS _tambah_indeks;
DELIMITER $$
CREATE PROCEDURE _tambah_kolom(IN p_tabel VARCHAR(64), IN p_kolom VARCHAR(64), IN p_definisi VARCHAR(500))
BEGIN
  IF (SELECT COUNT(*) FROM information_schema.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = p_tabel AND COLUMN_NAME = p_kolom) = 0 THEN
    SET @q = CONCAT('ALTER TABLE `', p_tabel, '` ADD COLUMN `', p_kolom, '` ', p_definisi);
    PREPARE s FROM @q; EXECUTE s; DEALLOCATE PREPARE s;
  END IF;
END$$
CREATE PROCEDURE _tambah_indeks(IN p_tabel VARCHAR(64), IN p_indeks VARCHAR(64), IN p_definisi VARCHAR(500))
BEGIN
  IF (SELECT COUNT(*) FROM information_schema.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = p_tabel AND INDEX_NAME = p_indeks) = 0 THEN
    SET @q = CONCAT('ALTER TABLE `', p_tabel, '` ADD ', p_definisi);
    PREPARE s FROM @q; EXECUTE s; DEALLOCATE PREPARE s;
  END IF;
END$$
DELIMITER ;

CALL _tambah_kolom('lokasi', 'zona_waktu', "VARCHAR(5) NOT NULL DEFAULT 'WIB' AFTER provinsi");

CALL _tambah_kolom('mesin', 'kode_unit',      "VARCHAR(20) NULL AFTER id");
CALL _tambah_kolom('mesin', 'jenis_mesin',    "VARCHAR(40) NOT NULL DEFAULT 'PCI DOCS 500' AFTER nama");
CALL _tambah_kolom('mesin', 'base_file_name', "VARCHAR(100) NULL AFTER jenis_mesin");
CALL _tambah_kolom('mesin', 'router',         "VARCHAR(40) NULL AFTER base_file_name");
CALL _tambah_kolom('mesin', 'status',         "ENUM('Aktif','Maintenance','Nonaktif') NOT NULL DEFAULT 'Aktif' AFTER mac");
CALL _tambah_indeks('mesin', 'uk_base_file_name', 'UNIQUE KEY uk_base_file_name (base_file_name)');
CALL _tambah_indeks('mesin', 'uk_kode_unit', 'UNIQUE KEY uk_kode_unit (kode_unit)');

UPDATE lokasi SET nama_rs = 'RS Contoh Semarang' WHERE kode = 'SEMARANG' AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Manado'   WHERE kode = 'MANADO'   AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Malang'   WHERE kode = 'MALANG'   AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Padang'   WHERE kode = 'PADANG'   AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Kupang'   WHERE kode = 'KUPANG'   AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Mataram'  WHERE kode = 'MATARAM'  AND nama_rs IS NULL;
UPDATE lokasi SET nama_rs = 'RS Contoh Jambi'    WHERE kode = 'JAMBI'    AND nama_rs IS NULL;
UPDATE lokasi SET zona_waktu = 'WITA' WHERE kode IN ('MANADO', 'KUPANG', 'MATARAM');

UPDATE mesin m JOIN lokasi l ON l.id = m.lokasi_id
SET m.kode_unit = 'DOCS-BDG-01', m.base_file_name = 'DOCS_500_Bandung', m.router = 'RUT241'
WHERE l.kode = 'BANDUNG' AND m.nama = 'DOCS500' AND m.kode_unit IS NULL;
UPDATE mesin m JOIN lokasi l ON l.id = m.lokasi_id
SET m.kode_unit = 'DOCS-SMG-01', m.router = 'RUT241'
WHERE l.kode = 'SEMARANG' AND m.nama = 'DOCS500' AND m.kode_unit IS NULL;

INSERT INTO mesin (kode_unit, lokasi_id, nama, jenis_mesin, status)
SELECT x.kode_unit, l.id, x.nama, x.jenis, 'Nonaktif'
FROM (SELECT 'MANADO' kode, 'DOCS-MND-01' kode_unit, 'DOCS200' nama, 'PCI DOCS 200' jenis
      UNION ALL SELECT 'MALANG',     'DOCS-MLG-01', 'DOCS200', 'PCI DOCS 200'
      UNION ALL SELECT 'PADANG',     'DOCS-PDG-01', 'DOCS200', 'PCI DOCS 200'
      UNION ALL SELECT 'KUPANG',     'DOCS-KPG-01', 'DOCS500', 'PCI DOCS 500'
      UNION ALL SELECT 'MATARAM',    'DOCS-MTR-01', 'DOCS200', 'PCI DOCS 200'
      UNION ALL SELECT 'JAMBI',      'DOCS-JMB-01', 'DOCS200', 'PCI DOCS 200') x
JOIN lokasi l ON l.kode = x.kode
WHERE NOT EXISTS (SELECT 1 FROM mesin m WHERE m.lokasi_id = l.id);

CREATE TABLE IF NOT EXISTS agregat_1menit (
  mesin_id   SMALLINT UNSIGNED NOT NULL,
  menit      DATETIME          NOT NULL,
  n          SMALLINT UNSIGNED NOT NULL,
  purity_avg DECIMAL(8,2) NULL, purity_min DECIMAL(8,2) NULL, purity_max DECIMAL(8,2) NULL,
  rt1_avg    DECIMAL(8,2) NULL, rt1_min    DECIMAL(8,2) NULL, rt1_max    DECIMAL(8,2) NULL,
  fvsa_avg   DECIMAL(8,2) NULL, fvsa_min   DECIMAL(8,2) NULL, fvsa_max   DECIMAL(8,2) NULL,
  purge_avg  DECIMAL(8,2) NULL, purge_min  DECIMAL(8,2) NULL, purge_max  DECIMAL(8,2) NULL,
  fbst_avg   DECIMAL(8,2) NULL, fbst_min   DECIMAL(8,2) NULL, fbst_max   DECIMAL(8,2) NULL,
  PRIMARY KEY (mesin_id, menit)
);

CREATE TABLE IF NOT EXISTS aturan_alarm (
  id                       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  jenis_mesin              VARCHAR(40)  NULL,
  mesin_id                 SMALLINT UNSIGNED NULL,
  parameter                ENUM('purity','rt1','fvsa','fbst','purge') NOT NULL,
  sumber                   ENUM('terbaru','avg1m') NOT NULL,
  normal_min               DECIMAL(8,2) NULL,
  normal_max               DECIMAL(8,2) NULL,
  maks1m_max               DECIMAL(8,2) NULL,
  kritis_min               DECIMAL(8,2) NULL,
  kritis_max               DECIMAL(8,2) NULL,
  kritis_syarat_vsa_jalan  TINYINT(1)   NOT NULL DEFAULT 0,
  delay_peringatan_detik   INT UNSIGNED NOT NULL DEFAULT 300,
  delay_kritis_detik       INT UNSIGNED NULL,
  pulih_detik              INT UNSIGNED NOT NULL DEFAULT 120,
  pulih_min                DECIMAL(8,2) NULL,
  naik_kritis_menit        INT UNSIGNED NULL,
  aktif                    TINYINT(1)   NOT NULL DEFAULT 1,
  diubah_oleh              VARCHAR(50)  NULL,
  diubah                   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_mesin (mesin_id),
  KEY ix_jenis (jenis_mesin)
);

INSERT INTO aturan_alarm (jenis_mesin, parameter, sumber, normal_min, normal_max, maks1m_max,
                          kritis_min, kritis_max, kritis_syarat_vsa_jalan,
                          delay_peringatan_detik, delay_kritis_detik, pulih_detik, pulih_min,
                          naik_kritis_menit, diubah_oleh)
SELECT * FROM (
  SELECT 'PCI DOCS 500' j, 'purity' p, 'terbaru' s, 91.0 nmin, NULL nmax, NULL m1, 90.0 kmin, NULL kmax, 0 sv, 120 dp, 60 dk,  120 pd, 91.5 pm, NULL nk, 'draf awal' o
  UNION ALL SELECT 'PCI DOCS 500', 'rt1',   'avg1m',   NULL, 225, 245, NULL, NULL, 0, 300, NULL, 300, NULL, 15,   'draf awal'
  UNION ALL SELECT 'PCI DOCS 500', 'fvsa',  'avg1m',   20,   24,  NULL, 5,   NULL, 0, 300, 60,   120, NULL, NULL, 'draf awal'
  UNION ALL SELECT 'PCI DOCS 500', 'fbst',  'avg1m',   24,   34,  NULL, 5,   NULL, 1, 300, 120,  120, NULL, NULL, 'draf awal'
  UNION ALL SELECT 'PCI DOCS 500', 'purge', 'terbaru', 135,  165, NULL, NULL, NULL, 0, 300, NULL, 300, NULL, 15,   'draf awal'
) d
WHERE NOT EXISTS (SELECT 1 FROM aturan_alarm a WHERE a.jenis_mesin = 'PCI DOCS 500' AND a.mesin_id IS NULL);

CREATE TABLE IF NOT EXISTS event_alarm (
  id               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  mesin_id         SMALLINT UNSIGNED NOT NULL,
  parameter        VARCHAR(10)  NOT NULL,
  level            ENUM('Peringatan','Kritis','Offline') NOT NULL,
  level_awal       ENUM('Peringatan','Kritis','Offline') NOT NULL,
  mulai            DATETIME     NOT NULL,
  naik_kritis      DATETIME     NULL,
  selesai          DATETIME     NULL,
  nilai_awal       DECIMAL(8,2) NULL,
  nilai_puncak     DECIMAL(8,2) NULL,
  nilai_terakhir   DECIMAL(8,2) NULL,
  keterangan       VARCHAR(255) NULL,
  saat_maintenance TINYINT(1)   NOT NULL DEFAULT 0,
  ack_oleh         VARCHAR(50)  NULL,
  ack_waktu        DATETIME     NULL,
  catatan          VARCHAR(500) NULL,
  notif_terakhir   DATETIME     NULL,
  eskalasi_waktu   DATETIME     NULL,
  KEY ix_mesin_aktif (mesin_id, selesai),
  KEY ix_mulai (mulai)
);

CREATE TABLE IF NOT EXISTS status_unit (
  mesin_id       SMALLINT UNSIGNED PRIMARY KEY,
  status         VARCHAR(20) NOT NULL,
  sejak          DATETIME    NOT NULL,
  startup_sampai DATETIME    NULL,
  data_terakhir  DATETIME    NULL,
  diperbarui     TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS riwayat_status (
  id       INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  mesin_id SMALLINT UNSIGNED NOT NULL,
  status   VARCHAR(20) NOT NULL,
  mulai    DATETIME    NOT NULL,
  selesai  DATETIME    NULL,
  KEY ix_mesin_mulai (mesin_id, mulai)
);

CREATE TABLE IF NOT EXISTS penerima_notifikasi (
  id                 INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  nama               VARCHAR(80)  NOT NULL,
  channel            ENUM('email','telegram') NOT NULL DEFAULT 'email',
  alamat             VARCHAR(200) NOT NULL,
  peran              ENUM('Teknisi','Supervisor') NOT NULL DEFAULT 'Teknisi',
  terima_peringatan  TINYINT(1) NOT NULL DEFAULT 1,
  terima_kritis      TINYINT(1) NOT NULL DEFAULT 1,
  terima_offline     TINYINT(1) NOT NULL DEFAULT 1,
  terima_pulih       TINYINT(1) NOT NULL DEFAULT 1,
  cakupan_lokasi     VARCHAR(200) NULL,
  jam_mulai          TIME NULL,
  jam_selesai        TIME NULL,
  aktif              TINYINT(1) NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS log_notifikasi (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  event_id    INT UNSIGNED NULL,
  jenis       VARCHAR(20)  NOT NULL,
  channel     VARCHAR(10)  NOT NULL,
  penerima    VARCHAR(200) NOT NULL,
  waktu_kirim DATETIME     NOT NULL,
  status      VARCHAR(120) NOT NULL,
  pesan       TEXT         NULL,
  KEY ix_event (event_id),
  KEY ix_waktu (waktu_kirim)
);

CREATE TABLE IF NOT EXISTS pengguna (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username        VARCHAR(50)  NOT NULL UNIQUE,
  nama            VARCHAR(80)  NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,
  peran           ENUM('Admin','Teknisi','Viewer') NOT NULL DEFAULT 'Viewer',
  aktif           TINYINT(1)   NOT NULL DEFAULT 1,
  dibuat          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  login_terakhir  DATETIME     NULL
);

CREATE TABLE IF NOT EXISTS audit (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  waktu       DATETIME     NOT NULL,
  pengguna    VARCHAR(50)  NOT NULL,
  aksi        VARCHAR(40)  NOT NULL,
  objek       VARCHAR(80)  NOT NULL,
  nilai_lama  JSON         NULL,
  nilai_baru  JSON         NULL,
  KEY ix_waktu (waktu)
);

CREATE TABLE IF NOT EXISTS heartbeat (
  nama  VARCHAR(40)  PRIMARY KEY,
  waktu DATETIME     NOT NULL,
  info  VARCHAR(255) NULL
);

DROP PROCEDURE IF EXISTS _tambah_kolom;
DROP PROCEDURE IF EXISTS _tambah_indeks;

CREATE USER IF NOT EXISTS 'gpi_dashboard'@'localhost' IDENTIFIED BY 'GANTI_PASSWORD';
GRANT SELECT, INSERT, UPDATE ON gpi_monitoring_system.* TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.telemetri      TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.agregat_1menit TO 'gpi_dashboard'@'localhost';
GRANT DELETE ON gpi_monitoring_system.riwayat_status TO 'gpi_dashboard'@'localhost';
GRANT SHOW VIEW, LOCK TABLES ON gpi_monitoring_system.* TO 'gpi_dashboard'@'localhost';

SELECT m.id, m.kode_unit, l.nama_rs, l.kota, m.jenis_mesin, m.base_file_name, m.status
FROM mesin m JOIN lokasi l ON l.id = m.lokasi_id ORDER BY m.id;
