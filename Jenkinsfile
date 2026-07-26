pipeline {
    agent any

    options {
        disableConcurrentBuilds()
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        IMAGE_NAME = 'manage-system'
        IMAGE_TAG = "${env.BUILD_NUMBER ?: 'local'}"
        PROJECT_CI = "manage-ci-${env.BUILD_NUMBER ?: 'local'}"
        COMPOSE_CI = 'docker-compose.ci.yml'
        COMPOSE_FULL = 'docker-compose.yml'
        PYTHONPATH = '.'
        FLASK_APP = 'app.main'
        DATABASE_URL = 'postgresql://postgres:ci_password@localhost:5432/inventory_db'
        E2E_BASE_URL = 'http://localhost:5000'
        CI_HOST = 'host.docker.internal'
        PATH = '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
        DOCKER = '/usr/local/bin/docker'
        DOCKER_COMPOSE = '/usr/local/bin/docker-compose'
        // Host path for docker -v (set in docker-compose jenkins service via HOST_PROJECT_DIR)
        HOST_MOUNT = "${env.HOST_PROJECT_DIR ?: '/workspace'}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh '${DOCKER} build -t ${IMAGE_NAME}:${IMAGE_TAG} .'
                sh '${DOCKER} run --rm -e DATABASE_URL=sqlite:///:memory: ${IMAGE_NAME}:${IMAGE_TAG} python -c "from app.main import app; assert app is not None"'
            }
        }

        stage('Tests') {
            parallel {
                stage('Unit tests') {
                    steps {
                        sh '${DOCKER} run --rm ${IMAGE_NAME}:${IMAGE_TAG} pytest tests/test_products.py tests/test_stock.py -v --tb=short'
                    }
                }

                stage('API / contract tests') {
                    steps {
                        sh '${DOCKER} run --rm ${IMAGE_NAME}:${IMAGE_TAG} pytest tests/test_contract.py -v --tb=short'
                    }
                }

                stage('Data / migration tests') {
                    steps {
                        sh '''
                            ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-data up -d db
                            for i in $(seq 1 30); do
                              ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-data exec -T db pg_isready -U postgres -d inventory_db && break
                              sleep 2
                            done
                            ${DOCKER} run --rm --network host \
                              -e PYTHONPATH=/app -e FLASK_APP=app.main \
                              -e DATABASE_URL=${DATABASE_URL} \
                              ${IMAGE_NAME}:${IMAGE_TAG} \
                              bash -lc "flask db upgrade && pytest tests/data/ -v --tb=short"
                        '''
                    }
                    post {
                        always {
                            sh '${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-data down -v || true'
                        }
                    }
                }
            }
        }

        stage('Coverage') {
            steps {
                sh '''
                    ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov up -d db
                    for i in $(seq 1 30); do
                      ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov exec -T db pg_isready -U postgres -d inventory_db && break
                      sleep 2
                    done
                    ${DOCKER} run --rm --network host \
                      -e PYTHONPATH=/app -e FLASK_APP=app.main \
                      -e DATABASE_URL=${DATABASE_URL} \
                      ${IMAGE_NAME}:${IMAGE_TAG} \
                      bash -lc "flask db upgrade && pytest tests/ -m 'not e2e' --cov=app --cov-report=xml --cov-report=term-missing --tb=short"
                '''
            }
            post {
                always {
                    sh '${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov down -v || true'
                }
            }
        }

        stage('Security') {
            steps {
                sh '''
                    ${DOCKER} run --rm ${IMAGE_NAME}:${IMAGE_TAG} \
                      bash -lc "pip install -q pip-audit && pip-audit -r requirements.txt"
                '''
            }
        }

        stage('E2E') {
            steps {
                sh '''
                    ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI} up -d --build
                    CI_HOST=${CI_HOST} bash scripts/wait-for-services.sh \
                      "Flask" "http://${CI_HOST}:5000/auth/login-page" \
                      "Keycloak" "http://${CI_HOST}:8080/realms/inventory-realm/.well-known/openid-configuration"
                    ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI} exec -T web flask db upgrade
                    COMPOSE_FILE=${COMPOSE_CI} COMPOSE_PROJECT=${PROJECT_CI} bash scripts/prepare-keycloak-e2e.sh
                    ${DOCKER} run --rm --network host \
                      -v "${HOST_MOUNT}:/app" -w /app \
                      -e PYTHONPATH=/app \
                      -e E2E_BASE_URL=${E2E_BASE_URL} \
                      -e E2E_ALICE_USER=alice_worker \
                      -e E2E_ALICE_PASSWORD=password123 \
                      -e E2E_MANAGER_USER=kratos_boss \
                      -e E2E_MANAGER_PASSWORD=password123 \
                      mcr.microsoft.com/playwright/python:v1.60.0-jammy \
                      bash -lc "pip install -q -r requirements.txt && pytest tests/e2e -m e2e -v --tb=short"
                '''
            }
            post {
                always {
                    sh '${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI} down -v || true'
                }
            }
        }

        stage('Full stack + k6 smoke') {
            steps {
                sh '''
                    if [ ! -f .env ]; then
                      cp .env.example .env
                      sed -i 's/your_password_here/ci_password/g; s/admin_username_here/admin/g; s/admin_password_here/admin/g' .env
                    fi
                    ${DOCKER_COMPOSE} -f ${COMPOSE_FULL} down -v --remove-orphans || true
                    CI_HOST=${CI_HOST} ${DOCKER_COMPOSE} -f ${COMPOSE_FULL} up -d --build
                    CI_HOST=${CI_HOST} bash scripts/wait-for-services.sh
                    ${DOCKER_COMPOSE} -f ${COMPOSE_FULL} exec -T web flask db upgrade
                    COMPOSE_FILE=${COMPOSE_FULL} bash scripts/prepare-keycloak-e2e.sh
                    CI_HOST=${CI_HOST} bash scripts/verify-stack.sh
                    mkdir -p reports
                    ${DOCKER} run --rm --network host \
                      -v "${HOST_MOUNT}:/app" -w /app \
                      -e BASE_URL=http://localhost:5000 \
                      -e KEYCLOAK_URL=http://localhost:8080 \
                      grafana/k6:0.53.0 run tests/k6/smoke-test.js
                '''
            }
            post {
                always {
                    sh '${DOCKER_COMPOSE} -f ${COMPOSE_FULL} down -v --remove-orphans || true'
                }
            }
        }

        stage('Docker image') {
            steps {
                sh '${DOCKER} tag ${IMAGE_NAME}:${IMAGE_TAG} ${IMAGE_NAME}:ci'
            }
        }
    }

    post {
        always {
            sh '''
                ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI} down -v || true
                ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-data down -v || true
                ${DOCKER_COMPOSE} -f ${COMPOSE_CI} -p ${PROJECT_CI}-cov down -v || true
                ${DOCKER_COMPOSE} -f ${COMPOSE_FULL} down -v --remove-orphans || true
            '''
        }
    }
}
