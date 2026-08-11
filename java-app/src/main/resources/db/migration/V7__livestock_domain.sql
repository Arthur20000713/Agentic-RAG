CREATE TABLE farm (
    id BIGINT NOT NULL AUTO_INCREMENT,
    owner_id BIGINT NOT NULL,
    farm_code VARCHAR(128) NOT NULL,
    name VARCHAR(255) NULL,
    location VARCHAR(255) NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_farm PRIMARY KEY (id),
    CONSTRAINT uk_farm_owner_code UNIQUE (owner_id, farm_code),
    CONSTRAINT uk_farm_id_owner UNIQUE (id, owner_id),
    CONSTRAINT fk_farm_owner FOREIGN KEY (owner_id) REFERENCES sys_user(id) ON DELETE RESTRICT,
    INDEX idx_farm_owner_updated (owner_id, updated_at)
);

CREATE TABLE animal (
    id BIGINT NOT NULL AUTO_INCREMENT,
    owner_id BIGINT NOT NULL,
    farm_id BIGINT NULL,
    animal_code VARCHAR(128) NOT NULL,
    species VARCHAR(64) NULL,
    breed VARCHAR(128) NULL,
    sex VARCHAR(32) NULL,
    birth_date DATE NULL,
    note VARCHAR(1000) NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_animal PRIMARY KEY (id),
    CONSTRAINT uk_animal_owner_code UNIQUE (owner_id, animal_code),
    CONSTRAINT uk_animal_id_owner UNIQUE (id, owner_id),
    CONSTRAINT fk_animal_owner FOREIGN KEY (owner_id) REFERENCES sys_user(id) ON DELETE RESTRICT,
    CONSTRAINT fk_animal_farm_owner FOREIGN KEY (farm_id, owner_id)
        REFERENCES farm(id, owner_id) ON DELETE RESTRICT,
    INDEX idx_animal_owner_updated (owner_id, updated_at),
    INDEX idx_animal_farm (farm_id)
);

CREATE TABLE measurement_record (
    id BIGINT NOT NULL AUTO_INCREMENT,
    owner_id BIGINT NOT NULL,
    animal_id BIGINT NOT NULL,
    measure_date DATE NOT NULL,
    body_height_cm DECIMAL(12,3) NULL,
    body_length_cm DECIMAL(12,3) NULL,
    chest_girth_cm DECIMAL(12,3) NULL,
    chest_depth_cm DECIMAL(12,3) NULL,
    chest_width_cm DECIMAL(12,3) NULL,
    weight_kg DECIMAL(12,3) NULL,
    source VARCHAR(64) NULL,
    confidence DECIMAL(5,4) NULL,
    algorithm_version VARCHAR(128) NULL,
    measurement_batch_id VARCHAR(128) NULL,
    note VARCHAR(1000) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT pk_measurement_record PRIMARY KEY (id),
    CONSTRAINT fk_measurement_record_owner FOREIGN KEY (owner_id)
        REFERENCES sys_user(id) ON DELETE RESTRICT,
    CONSTRAINT fk_measurement_record_animal_owner FOREIGN KEY (animal_id, owner_id)
        REFERENCES animal(id, owner_id) ON DELETE RESTRICT,
    CONSTRAINT chk_measurement_record_values CHECK (
        body_height_cm IS NOT NULL OR body_length_cm IS NOT NULL
        OR chest_girth_cm IS NOT NULL OR chest_depth_cm IS NOT NULL
        OR chest_width_cm IS NOT NULL OR weight_kg IS NOT NULL
    ),
    CONSTRAINT chk_measurement_record_non_negative CHECK (
        (body_height_cm IS NULL OR body_height_cm >= 0)
        AND (body_length_cm IS NULL OR body_length_cm >= 0)
        AND (chest_girth_cm IS NULL OR chest_girth_cm >= 0)
        AND (chest_depth_cm IS NULL OR chest_depth_cm >= 0)
        AND (chest_width_cm IS NULL OR chest_width_cm >= 0)
        AND (weight_kg IS NULL OR weight_kg >= 0)
    ),
    CONSTRAINT chk_measurement_record_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    INDEX idx_measurement_animal_date (animal_id, measure_date, id),
    INDEX idx_measurement_owner_created (owner_id, created_at)
);
